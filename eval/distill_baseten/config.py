"""Baseten Training job for the one tuning run in docs/DISTILLATION.md: one H100, stopped by a hard time limit."""
from truss.base.truss_config import AcceleratorSpec
from truss_train import CacheConfig, CheckpointingConfig, Compute, Image, Runtime, TrainingJob, TrainingProject

training_project = TrainingProject(
    name="diocle-distill",
    job=TrainingJob(
        image=Image(base_image="pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime"),
        compute=Compute(accelerator=AcceleratorSpec(accelerator="H100", count=1)),
        runtime=Runtime(start_commands=["chmod +x ./run.sh && ./run.sh"], cache_config=CacheConfig(enabled=True),
                        checkpointing_config=CheckpointingConfig(enabled=True)),
    ),
)
