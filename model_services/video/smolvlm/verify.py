"""Load the pinned SmolVLM2 model and report its local runtime footprint."""

from model_services.video.smolvlm.runtime import SmolVLMRuntime


def main() -> None:
    runtime = SmolVLMRuntime()
    parameters = sum(parameter.numel() for parameter in runtime.model.parameters())
    print(f"SmolVLM2 ready on {runtime.device}; parameters={parameters:,}")


if __name__ == "__main__":
    main()
