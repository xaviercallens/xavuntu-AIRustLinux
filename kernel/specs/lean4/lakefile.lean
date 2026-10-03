import Lake
open Lake DSL

package mvk_specs where
  -- MVK v8.4.0 Formal Specifications
  version := v!"8.4.0"
  precompileModules := true

@[default_target]
lean_lib MVK where
  roots := #[`MVK]
  globs := #[.submodules `MVK]
