import jax
import jax.numpy as jnp

key = jax.random.PRNGKey(0)
a = jax.random.normal(key, (512, 512))
b = jax.random.normal(key, (512, 512))
c = jnp.dot(a, b).block_until_ready()
print(float(jnp.sum(c)))
