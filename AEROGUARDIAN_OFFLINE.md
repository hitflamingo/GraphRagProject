# AeroGuardian Offline Workflow

The default engineering validation path runs without Neo4j, OpenAI/Qwen, AP-SAM, or Halcon.

Run the passing path:

```powershell
python -m src.swarm.cli --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --part-id OFFLINE_PASS --measurements examples/offline_measurements_pass.json --quiet
```

Run the anomaly path:

```powershell
python -m src.swarm.cli --drawing data/xizi_part_1.png --process-card data/xizi_card_1.xlsx --part-id OFFLINE_ANOMALY --measurements examples/offline_measurements_anomaly.json --output results/offline_anomaly.json --quiet
```

The anomaly path produces `measurement_data`, `anomaly_event`, `defect_record`, `graph_cot_report`, and `inspection_plan`.

Neo4j/OpenAI-backed behavior remains optional and should be validated with explicitly enabled integration tests.
