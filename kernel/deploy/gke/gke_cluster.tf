# ============================================================
# GKE Standard Cluster with Nested Virtualization
# For MVK Rust Kernel Performance & Chaos Testing
# ============================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --------------------------------------------------
# VPC Network (Dataplane V2 / eBPF)
# --------------------------------------------------
resource "google_compute_network" "mvk_vpc" {
  name                    = "${var.cluster_name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "mvk_subnet" {
  name          = "${var.cluster_name}-subnet"
  network       = google_compute_network.mvk_vpc.id
  ip_cidr_range = "10.0.0.0/20"
  region        = var.region

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.4.0.0/14"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.8.0.0/20"
  }
}

# --------------------------------------------------
# GKE Standard Cluster
# --------------------------------------------------
resource "google_container_cluster" "mvk_cluster" {
  name     = var.cluster_name
  location = var.zone

  # Use Dataplane V2 (eBPF-based networking)
  datapath_provider = "ADVANCED_DATAPATH"

  # VPC-native cluster
  network    = google_compute_network.mvk_vpc.id
  subnetwork = google_compute_subnetwork.mvk_subnet.id

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Monitoring & Logging
  monitoring_config {
    managed_prometheus {
      enabled = true
    }
  }

  # Release channel
  release_channel {
    channel = "REGULAR"
  }

  deletion_protection = false
}

# --------------------------------------------------
# Benchmark Node Pool (Nested Virtualization)
# --------------------------------------------------
resource "google_container_node_pool" "benchmark_nodes" {
  name       = "benchmark-nodes"
  cluster    = google_container_cluster.mvk_cluster.id
  node_count = var.benchmark_node_count

  node_config {
    machine_type = var.benchmark_machine_type
    image_type   = "UBUNTU_CONTAINERD"

    # Enable nested virtualization for QEMU/KVM
    advanced_machine_features {
      enable_nested_virtualization = true
    }

    # Use Spot VMs for cost savings (60% cheaper)
    spot = var.use_spot_vms

    disk_size_gb = 100
    disk_type    = "pd-ssd"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      role = "benchmark"
      app  = "mvk-kernel"
    }

    taint {
      key    = "benchmark"
      value  = "true"
      effect = "NO_SCHEDULE"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = false
  }
}

# --------------------------------------------------
# Control Plane Node Pool (Chaos Mesh + Prometheus)
# --------------------------------------------------
resource "google_container_node_pool" "control_nodes" {
  name       = "control-nodes"
  cluster    = google_container_cluster.mvk_cluster.id
  node_count = 1

  node_config {
    machine_type = "n2d-standard-4"
    image_type   = "UBUNTU_CONTAINERD"
    spot         = var.use_spot_vms

    disk_size_gb = 50
    disk_type    = "pd-ssd"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = {
      role = "control"
    }
  }
}

# --------------------------------------------------
# Outputs
# --------------------------------------------------
output "cluster_name" {
  value = google_container_cluster.mvk_cluster.name
}

output "cluster_endpoint" {
  value     = google_container_cluster.mvk_cluster.endpoint
  sensitive = true
}

output "get_credentials_command" {
  value = "gcloud container clusters get-credentials ${var.cluster_name} --zone ${var.zone} --project ${var.project_id}"
}
