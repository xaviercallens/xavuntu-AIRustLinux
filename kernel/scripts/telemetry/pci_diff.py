#!/usr/bin/env python3
"""Independent oracle for the PCI topology telemetry campaign.

Compares RunuX's real driver_pci_probe/driver_pci_access output (captured
by pci_topology_run.sh into a tarball of per-run JSON files) against an
*independent* ground truth: the Linux kernel's own sysfs presentation of
the same PCI devices, captured in the same tarball at the same time.

RunuX checking itself proves nothing -- this script never trusts the
Rust tool's own self-reported "sysfs_class_matches" field, and instead
re-derives every comparison from the raw sysfs snapshot files.

Usage: pci_diff.py TARBALL [TARBALL ...] --out OUT_DIR
Exits non-zero if any run has a BDF-set mismatch, an identity-field
mismatch, an unmasked config-byte mismatch, or if dmesg shows new
warnings/errors after the run.
"""
import argparse
import csv
import json
import statistics
import sys
import tarfile
from pathlib import Path


def read_sysfs_snapshot(tar: tarfile.TarFile) -> dict:
    """Returns {bdf: {vendor, device, class, subclass, driver, config_hex}}."""
    devices = {}
    for member in tar.getmembers():
        parts = member.name.split("/")
        if len(parts) >= 3 and parts[0] == "." and parts[1] == "sysfs":
            bdf = parts[2]
            devices.setdefault(bdf, {})
            if len(parts) == 4:
                fname = parts[3]
                content = tar.extractfile(member)
                if content is None:
                    continue
                raw = content.read().decode(errors="replace").strip()
                if fname in ("vendor", "device"):
                    devices[bdf][fname] = raw.replace("0x", "").lower().zfill(4)
                elif fname == "class":
                    # sysfs class is 6 hex digits: class(2) + subclass(2) + progif(2)
                    hexval = raw.replace("0x", "").lower().zfill(6)
                    devices[bdf]["class"] = hexval[0:2]
                    devices[bdf]["subclass"] = hexval[2:4]
                elif fname == "driver_name":
                    devices[bdf]["driver"] = raw
                elif fname == "config":
                    pass  # binary file, handled separately below
    # Binary config files need a second pass via extractfile with 'rb'
    for member in tar.getmembers():
        if member.name.endswith("/config") and "/sysfs/" in member.name:
            bdf = member.name.split("/")[2]
            content = tar.extractfile(member)
            if content is not None:
                devices.setdefault(bdf, {})["config_hex"] = content.read().hex()
    return devices


def bdf_from_runux(addr_bus: int, addr_dev: int, addr_func: int) -> str:
    return f"0000:{addr_bus:02x}:{addr_dev:02x}.{addr_func:x}"


def analyze_tarball(path: Path, out_dir: Path):
    campaign_id = path.stem.replace(".tar", "")
    with tarfile.open(path, "r:gz") as tar:
        sysfs = read_sysfs_snapshot(tar)

        dmesg_pre, dmesg_post = "", ""
        for member in tar.getmembers():
            if member.name.endswith("dmesg_pre.log"):
                dmesg_pre = tar.extractfile(member).read().decode(errors="replace")
            elif member.name.endswith("dmesg_post.log"):
                dmesg_post = tar.extractfile(member).read().decode(errors="replace")

        pre_lines = set(dmesg_pre.splitlines())
        post_lines = dmesg_post.splitlines()
        new_dmesg_lines = [
            l for l in post_lines
            if l not in pre_lines and any(w in l for w in ("error", "Error", "ERROR", "warn", "Warn", "WARN"))
        ]

        run_files = sorted(
            [m for m in tar.getmembers() if m.name.startswith("./runs/run_") and m.name.endswith(".json")],
            key=lambda m: int(m.name.split("run_")[1].split(".json")[0]),
        )

        runs_rows = []
        devices_rows = []
        enum_times_ns = []
        any_failure = False

        for member in run_files:
            iter_num = int(member.name.split("run_")[1].split(".json")[0])
            content = tar.extractfile(member)
            if content is None:
                continue
            try:
                data = json.loads(content.read().decode())
            except json.JSONDecodeError:
                runs_rows.append({"campaign_id": campaign_id, "iter": iter_num, "parse_error": True})
                any_failure = True
                continue

            enum_wall_ns = data.get("enum_wall_ns", 0)
            enum_times_ns.append(enum_wall_ns)
            runux_devices = data.get("devices", [])
            runux_bdfs = {d["bdf"] for d in runux_devices}
            sysfs_bdfs = set(sysfs.keys())

            bdf_set_equal = runux_bdfs == sysfs_bdfs
            identity_mismatches = 0
            config_mismatches = 0

            for d in runux_devices:
                bdf = d["bdf"]
                sysfs_dev = sysfs.get(bdf, {})
                vendor_match = d["vendor"] == sysfs_dev.get("vendor")
                device_match = d["device"] == sysfs_dev.get("device")
                class_match = d["class"] == sysfs_dev.get("class")
                subclass_match = d["subclass"] == sysfs_dev.get("subclass")
                if not (vendor_match and device_match and class_match and subclass_match):
                    identity_mismatches += 1

                config_match = None
                if "config_bytes_hex" in d and "config_hex" in sysfs_dev:
                    runux_cfg = d["config_bytes_hex"].lower()
                    sysfs_cfg = sysfs_dev["config_hex"].lower()[: len(runux_cfg)]
                    config_match = runux_cfg == sysfs_cfg
                    if config_match is False:
                        config_mismatches += 1

                devices_rows.append({
                    "campaign_id": campaign_id,
                    "iter": iter_num,
                    "bdf": bdf,
                    "vendor": d["vendor"],
                    "device": d["device"],
                    "class": d["class"],
                    "subclass": d["subclass"],
                    "driver_bound": d.get("driver_bound"),
                    "sysfs_driver_name": sysfs_dev.get("driver", ""),
                    "identity_match": vendor_match and device_match and class_match and subclass_match,
                    "config_match": config_match,
                })

            if not bdf_set_equal or identity_mismatches > 0 or config_mismatches > 0:
                any_failure = True

            runs_rows.append({
                "campaign_id": campaign_id,
                "iter": iter_num,
                "enum_wall_ns": enum_wall_ns,
                "device_count": len(runux_devices),
                "sysfs_device_count": len(sysfs),
                "bdf_set_equal": bdf_set_equal,
                "identity_mismatches": identity_mismatches,
                "config_mismatches": config_mismatches,
            })

        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / f"{campaign_id}_runs.csv", "w", newline="") as f:
            if runs_rows:
                writer = csv.DictWriter(f, fieldnames=sorted({k for r in runs_rows for k in r}))
                writer.writeheader()
                writer.writerows(runs_rows)
        with open(out_dir / f"{campaign_id}_devices.csv", "w", newline="") as f:
            if devices_rows:
                writer = csv.DictWriter(f, fieldnames=sorted({k for r in devices_rows for k in r}))
                writer.writeheader()
                writer.writerows(devices_rows)

        print(f"=== {campaign_id} ===")
        print(f"Runs: {len(runs_rows)}, sysfs devices: {len(sysfs)}")
        if enum_times_ns:
            median_ns = statistics.median(enum_times_ns)
            print(f"Median enumeration wall time: {median_ns:.0f}ns ({median_ns/1e6:.3f}ms) over n={len(enum_times_ns)}")
        clean_runs = sum(1 for r in runs_rows if r.get("bdf_set_equal") and r.get("identity_mismatches", 1) == 0)
        print(f"Clean runs (BDF set + identity match sysfs): {clean_runs}/{len(runs_rows)}")
        if new_dmesg_lines:
            print(f"NEW dmesg warning/error lines after run: {len(new_dmesg_lines)}")
            for l in new_dmesg_lines[:5]:
                print(f"  {l}")
            any_failure = True
        else:
            print("No new dmesg warning/error lines after run.")

        return any_failure


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tarballs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    any_failure = False
    for tb in args.tarballs:
        if analyze_tarball(tb, args.out):
            any_failure = True
        print()

    if any_failure:
        print("FAIL: at least one campaign had a mismatch or new dmesg warning/error.", file=sys.stderr)
        sys.exit(1)
    print("PASS: all campaigns clean (sysfs identity match, no new dmesg warnings/errors).")


if __name__ == "__main__":
    main()
