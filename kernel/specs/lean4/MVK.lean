-- MVK v9.3.1 Formal Specifications Root Module
-- Auto-generated module index

-- Phase 1: Boot Subsystem
import MVK.Phase1.Printk
import MVK.Phase1.ArchSetup
import MVK.Phase1.InitMain

-- Phase 2: Memory Management
import MVK.Phase2.Common
import MVK.Phase2.PageAlloc
import MVK.Phase2.Slab

-- Phase 3: Netfilter Core
import MVK.Phase3.ConntrackCore
import MVK.Phase3.ConntrackTCP
import MVK.Phase3.ConntrackUDP
import MVK.Phase3.ConntrackICMP
import MVK.Phase3.ConntrackICMPv6
import MVK.Phase3.ConntrackGeneric
import MVK.Phase3.ConntrackSCTP
import MVK.Phase3.ConntrackDCCP
import MVK.Phase3.NatCore
import MVK.Phase3.NatProto

-- Phase 4: Network Stack - IPv4/IPv6 Core & Routing
import MVK.Phase4.IPv4IPv6.AfInet
import MVK.Phase4.IPv4IPv6.AfInet6
import MVK.Phase4.Routing.FibSemantics
import MVK.Phase4.ARP
import MVK.Phase4.IPv4IPv6.Tcpv6
import MVK.Phase4.UDP
import MVK.Phase4.ICMP

-- Phase 5: IPv6 Advanced
import MVK.Phase5.IPv6
import MVK.Phase6.Routing

-- Phase 7: Formal Requirements
import MVK.Phase7.Netfilter
import MVK.Phase7.Sockets

-- Phase 8: Scheduling
import MVK.Phase8.Scheduling

-- Phase 9: Memory Allocation
import MVK.Phase9.Memory
-- Phase 11: Hardware Drivers
import MVK.Phase11.Hardware

-- Phase 12: GCP Baremetal Drivers
import MVK.Phase12.GCP_Drivers

-- Runux Core Defenses: Active Defense Pipeline & Kernel Isolation
import MVK.RunuxDefenses

-- Phase 13: GPU Compute Subsystem, IOMMU DMA Containment & HMM
import MVK.Phase13.GpuCompute

-- Phase 14: Quantum LTN
import MVK.QuantumLTN.FuzzyLogic
import MVK.QuantumLTN.PolarQuant
import MVK.SystolicAlignment
