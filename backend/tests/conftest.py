import os

# Scripted FunctionModel/TestModel responses answer through the final_result output tool,
# so agents must be built in "tool" mode; set before any app module creates them.
os.environ["AGENT_OUTPUT_MODE"] = "tool"
