# Model-pipeline smoke corpus

This deliberately small corpus verifies the local BanglaBERT fine-tuning
pipeline, its label checks, and metrics output. Every sentence is synthetic;
it is **not** crisis data, independently reviewed data, a benchmark, or
suitable for deployment. The resulting checkpoint must never be configured as
`PROTIDHONI_FINE_TUNED_MODEL_PATH`.

Before enabling a trained classifier, replace this corpus with separately
reviewed, consented, representative data stored in the team's approved private
location. Keep a held-out evaluation set, document its review, and evaluate
per class as well as overall accuracy and macro-F1.

Each JSONL record has `text` and a frozen report `type`. The training command
requires at least four training records and one evaluation record for every
frozen type.
