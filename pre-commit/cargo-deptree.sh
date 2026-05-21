#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
out_file="${1:-$root/.cargo/cargo-deptree.gv}"

cd "$root"
mkdir -p "$root/.cargo"

cargo metadata --format-version 1 --all-features --no-deps \
| jq -c '
  def dep_kind:
    if . == null then "normal" else . end;

  . as $meta
  | ($meta.packages
      | map(select(.id as $id | ($meta.workspace_members | index($id))))
    ) as $packages
  | ($packages
      | map({key: (.manifest_path | sub("/Cargo.toml$"; "")), value: .name})
      | from_entries
    ) as $workspace_by_path
  | $packages[]
  | . as $pkg
  | $pkg.dependencies[]
  | select(.path != null)
  | select(($workspace_by_path[.path] // null) != null)
  | {
      source: $pkg.name,
      target: $workspace_by_path[.path],
      kind: (.kind | dep_kind),
      target_cfg: (.target // null)
    }
' \
| jq -s -r '
  def edge_style($kind):
    if $kind == "build" then "dotted"
    elif $kind == "dev" then "dashed"
    else "solid"
    end;

  def edge_color($kind):
    if $kind == "build" then "#d35400"
    elif $kind == "dev" then "#2980b9"
    else "#2c3e50"
    end;

  "digraph \"wanguard-dependencies\" {",
  "  graph [rankdir=LR, splines=true, overlap=false, pad=0.2];",
  "  node [shape=box, style=\"rounded,filled\", fillcolor=\"#f8f8f8\", color=\"#b0b0b0\", fontname=\"Helvetica\"];",
  "  edge [fontname=\"Helvetica\", arrowsize=0.7];",
  "",
  (.[] | "  " + (.source | @json) + " -> " + (.target | @json)
    + " [label="
    + ((.kind + (if .target_cfg != null then "\\ncfg: " + .target_cfg else "" end)) | @json)
    + ", style=" + (edge_style(.kind) | @json)
    + ", color=" + (edge_color(.kind) | @json)
    + "];"
  ),
  "}"
' | nop > "$out_file"

dot -Tsvg "$out_file" -o "${out_file%.gv}.svg"
