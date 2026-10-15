import os

# Scripted FunctionModel/TestModel responses answer through the final_result output tool,
# so agents must be built in "tool" mode; set before any app module creates them.
os.environ["AGENT_OUTPUT_MODE"] = "tool"

# The default model chains (DeepInfra, NVIDIA, Gemini) are built at import, and their
# clients refuse to be built without a key. Tests never call a real model, so a
# placeholder lets CI run without .env.
for _key in ("DEEPINFRA_API_KEY", "NVIDIA_API_KEY", "GOOGLE_API_KEY"):
    os.environ.setdefault(_key, "test-placeholder")
