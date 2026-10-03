variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone for zonal cluster"
  type        = string
  default     = "us-central1-a"
}

variable "cluster_name" {
  description = "GKE cluster name"
  type        = string
  default     = "mvk-benchmark"
}

variable "benchmark_machine_type" {
  description = "Machine type for benchmark nodes"
  type        = string
  default     = "n2d-standard-8"
}

variable "benchmark_node_count" {
  description = "Number of benchmark nodes"
  type        = number
  default     = 3
}

variable "use_spot_vms" {
  description = "Use Spot VMs for cost savings (~60% cheaper)"
  type        = bool
  default     = true
}
