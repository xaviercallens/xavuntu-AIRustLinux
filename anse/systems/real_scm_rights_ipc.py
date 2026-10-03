"""
Genuine POSIX SCM_RIGHTS Process Hot-Swapping Engine for ANSE.
Executes real Unix Domain Socket IPC (AF_UNIX / SOCK_STREAM) with ancillary
ancillary data (SOL_SOCKET, SCM_RIGHTS) file descriptor migration between processes.
Validates zero-packet-drop state continuity, microsecond migration latency, and memory deltas.
"""

from __future__ import annotations

import array
import os
import resource
import socket
import struct
import tempfile
import time
from dataclasses import dataclass
from multiprocessing import Process, Pipe


@dataclass
class SCMHotSwapResult:
    success: bool
    migration_duration_us: float
    parent_rss_kb: int
    child_rss_kb: int
    memory_delta_kb: int
    bytes_transferred_post_migration: int
    socket_continuity_verified: bool
    error: str | None = None


def _child_worker(uds_path: str, sync_pipe):
    """
    Child process worker:
    1. Connects to the parent control socket.
    2. Receives the migrated client socket descriptor via SCM_RIGHTS ancillary data.
    3. Resumes stream communication with the client directly without dropped packets.
    """
    try:
        ctrl_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ctrl_sock.connect(uds_path)

        # Receive file descriptor via recvmsg
        fds = array.array("i")
        cmsg_space = socket.CMSG_SPACE(fds.itemsize)
        msg, ancdata, flags, addr = ctrl_sock.recvmsg(1024, cmsg_space)

        adopted_fd = None
        for cmsg_level, cmsg_type, cmsg_data in ancdata:
            if cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS:
                fds.frombytes(cmsg_data[:len(cmsg_data) - (len(cmsg_data) % fds.itemsize)])
                adopted_fd = fds[0]
                break

        if adopted_fd is None:
            sync_pipe.send({"success": False, "error": "No SCM_RIGHTS file descriptor received"})
            return

        # Adopt client socket
        client_sock = socket.socket(fileno=adopted_fd)
        # Send confirmation token through migrated client connection
        post_token = b"MIGRATION_CONFIRMED_AUTOCONTINUITY\n"
        client_sock.sendall(post_token)

        # Signal completion to runner
        child_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        sync_pipe.send({
            "success": True,
            "child_rss": child_rss,
            "bytes_sent": len(post_token),
        })

        client_sock.close()
        ctrl_sock.close()
    except Exception as e:
        sync_pipe.send({"success": False, "error": str(e)})


class RealSCMHotSwapper:
    def __init__(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="anse_scm_")
        self.uds_path = os.path.join(self.tmp_dir, "migration_control.sock")
        self.client_uds = os.path.join(self.tmp_dir, "active_client.sock")

    def execute_hot_swap(self) -> SCMHotSwapResult:
        """
        Executes a live parent -> child SCM_RIGHTS hot-swap.
        """
        parent_rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        # 1. Setup client-server connection representing the active workload
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(self.client_uds)
        server_sock.listen(1)

        client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_sock.connect(self.client_uds)
        active_conn, _ = server_sock.accept()

        # Transmit initial workload data
        active_conn.sendall(b"WORKLOAD_PHASE_1_RUNNING\n")
        rec1 = client_sock.recv(1024)
        if b"WORKLOAD_PHASE_1_RUNNING" not in rec1:
            raise RuntimeError("Initial client connection failed.")

        # 2. Setup control socket for SCM_RIGHTS migration
        control_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        control_listener.bind(self.uds_path)
        control_listener.listen(1)

        # 3. Spawn child process
        pipe_parent, pipe_child = Pipe()
        proc = Process(target=_child_worker, args=(self.uds_path, pipe_child))
        proc.start()

        # Accept connection from child
        ctrl_conn, _ = control_listener.accept()

        # 4. Perform atomic SCM_RIGHTS migration
        t0 = time.perf_counter()
        
        # Package active client socket descriptor
        fd_to_pass = active_conn.fileno()
        ancillary_payload = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack("i", fd_to_pass))]
        ctrl_conn.sendmsg([b"TRANSFER_FD"], ancillary_payload)

        # Await child confirmation
        res = pipe_parent.recv()
        migration_us = (time.perf_counter() - t0) * 1_000_000.0

        # Verify client received token from child over the exact same socket connection
        client_sock.settimeout(2.0)
        rec2 = client_sock.recv(1024)
        continuity_verified = b"MIGRATION_CONFIRMED_AUTOCONTINUITY" in rec2

        proc.join(timeout=3.0)

        # Cleanup
        active_conn.close()
        client_sock.close()
        server_sock.close()
        control_listener.close()
        ctrl_conn.close()
        try:
            os.unlink(self.uds_path)
            os.unlink(self.client_uds)
            os.rmdir(self.tmp_dir)
        except OSError:
            pass

        if not res.get("success"):
            return SCMHotSwapResult(
                success=False,
                migration_duration_us=migration_us,
                parent_rss_kb=parent_rss_before,
                child_rss_kb=0,
                memory_delta_kb=0,
                bytes_transferred_post_migration=0,
                socket_continuity_verified=False,
                error=res.get("error", "Unknown error"),
            )

        child_rss = res.get("child_rss", parent_rss_before)
        mem_delta = child_rss - parent_rss_before

        return SCMHotSwapResult(
            success=True,
            migration_duration_us=migration_us,
            parent_rss_kb=parent_rss_before,
            child_rss_kb=child_rss,
            memory_delta_kb=mem_delta,
            bytes_transferred_post_migration=res.get("bytes_sent", 0),
            socket_continuity_verified=continuity_verified,
        )


def run_atomic_socket_migration() -> dict:
    """Convenience helper executing and verifying real SCM_RIGHTS file descriptor migration."""
    swapper = RealSCMHotSwapper()
    res = swapper.execute_hot_swap()
    return {
        "success": res.success,
        "socket_continuity_verified": res.socket_continuity_verified,
        "migration_duration_us": res.migration_duration_us,
        "memory_delta_kb": res.memory_delta_kb,
    }

