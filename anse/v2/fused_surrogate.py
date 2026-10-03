import torch

@torch.jit.script
def fast_fused_surrogate_filter(
    candidate_latents: torch.Tensor,
    weights: torch.Tensor,
    bias: torch.Tensor,
    top_k: int
) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Autopoietically generated fused kernel (simulating V3's optimization over V2).
    Eliminates Python overhead entirely using TorchScript graph compilation.
    """
    # Linear projection: Energy prediction
    energy_preds = torch.matmul(candidate_latents, weights.t()) + bias
    energy_preds = energy_preds.squeeze(-1)
    
    # Sort and select Top-K (lowest energy)
    topk_vals, topk_indices = torch.topk(energy_preds, top_k, largest=False)
    
    return topk_indices, topk_vals
