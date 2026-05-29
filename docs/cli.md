# Aether CLI Reference

Most people should use Aether through Codex natural language requests. The CLI is mainly for validation, scripting, and debugging.

## Health And Config

```bash
aether doctor
aether config show
```

## Visual Memory

List reusable visual memories:

```bash
aether visual-asset list --summary
aether visual-asset list --type style --summary
aether visual-asset list --query "rain neon" --summary
```

Inspect one memory when you need exact stored details:

```bash
aether visual-asset get <visual_asset_id>
aether visual-asset evidence <visual_asset_id>
aether visual-asset quality <visual_asset_id>
```

## Save Visual Candidates

Reference-image analysis is normally handled by `$aether-orchestrator`. For scripted ingestion:

```bash
aether asset ingest --path reference.png --kind reference
python plugins/aether/skills/visual-asset-capture/scripts/save_candidate_batch.py --json plugins/aether/examples/visual-asset-candidates.json --summary-only
```

Confirm all asset candidates in one batch:

```bash
aether visual-asset candidates confirm-batch <candidate_batch_id>
```

For one-by-one decisions:

```bash
aether visual-asset candidates decide <candidate_id> create_new
aether visual-asset candidates decide <candidate_id> attach_evidence --target-asset-id <visual_asset_id>
aether visual-asset candidates decide <candidate_id> inherit_variant --target-asset-id <visual_asset_id>
aether visual-asset candidates decide <candidate_id> ignore --cleanup
```

## Visual Systems And Recipes

```bash
aether visual-system list --summary
aether visual-system create --json plugins/aether/examples/visual-system.json
aether recipe list --summary
aether recipe create --json plugins/aether/examples/recipe.json
```

## Prompt Refinement

Compose a prompt with existing visual memory:

```bash
aether prompt compose --source-prompt "a lonely girl in a future city" --query "rain neon" --save
aether prompt compose --source-prompt "a quiet character portrait" --system-id <visual_system_id> --recipe-id <recipe_id>
```

Save a complete prompt record:

```bash
aether prompt save --json plugins/aether/examples/prompt-record.json
python plugins/aether/skills/prompt-refine/scripts/save_prompt_record.py --json plugins/aether/examples/prompt-record.json --emit-confirmation
```

## Generation History

Record a generation run:

```bash
aether generation record --json plugins/aether/examples/generation-run.json
```

Review history and feedback:

```bash
aether generation list
aether generation get <generation_run_id>
aether generation stats
aether generation suggest <generation_run_id>
aether generation feedback <generation_run_id> --liked true --notes "usable style match"
```

## Asset Inventory

```bash
aether asset list --kind generated
aether asset stats
aether asset duplicates --kind generated
aether asset unreferenced --kind generated
```

## Validation

```bash
aether validate visual-asset --json plugins/aether/examples/visual-asset.json
aether validate visual-asset-candidate --json plugins/aether/examples/visual-asset-candidates.json
aether validate prompt --json plugins/aether/examples/prompt-record.json
aether validate generation --json plugins/aether/examples/generation-run.json
```
