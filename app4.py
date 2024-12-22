import os
from llama_stack_client import LlamaStackClient
from tools import SANDBOX_DIR, TOOLS, run_tool
import json

# Works:
# MODEL_ID = "meta-llama/Llama-3.1-405B-Instruct-FP8"
# MODEL_ID = "meta-llama/Llama-3.3-70B-Instruct"
# MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"

MODEL_ID = "meta-llama/Llama-3.2-3B-Instruct"
# MODEL_ID = "meta-llama/Llama-3.2-1B-Instruct"


if "3.2" in MODEL_ID or "3.3" in MODEL_ID:
    tool_prompt_format = "python_list"
else:
    tool_prompt_format = "json"

# Number of code review cycles
CODE_REVIEW_CYCLES = 5

# No limit on output tokens
MAX_TOKENS = 200_000


PROGRAM_OBJECTIVE="a web server that has an API endpoint that translates text from English to French."

CODER_AGENT_SYSTEM_PROMPT=f"""
You are a software engineer who is writing code to build a python codebase: {PROGRAM_OBJECTIVE}.
"""

REVIEWER_AGENT_SYSTEM_PROMPT=f"""
You are a senior software engineer who is reviewing the codebase that was created by another software engineer.
The program is {PROGRAM_OBJECTIVE}.
If you think the codebase is good enough to ship, please say LGTM.
"""


def get_codebase_contents():
    contents = ""
    for root, dirs, files in os.walk(SANDBOX_DIR):
        for file in files:
            # concatenate the file name
            contents += f"file: {file}:\n"
            with open(os.path.join(root, file), "r") as f:
                contents += f.read()
            contents += "\n\n"
    return contents


BLUE = "\033[94m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
RESET = "\033[0m"


client = LlamaStackClient(base_url=f"http://localhost:{os.environ['LLAMA_STACK_PORT']}")

review_feedback = None
for i in range(1, CODE_REVIEW_CYCLES + 1):
    print(f"{BLUE}Coder Agent - Creating Plan - Iteration {i}{RESET}")
    if review_feedback:
        prompt_feedback = f"""
        One of your peers has provided the following feedback:
        {review_feedback}
        Please adjust the plan to address the feedback.

        
        """
    else:
        prompt_feedback = ""

    prompt =f"""
        Request:
        Create a step by step plan to complete the task of creating a codebase that will print "Hello, World!".
        You have 3 different operations you can perform. You can create a file, update a file, or delete a file.
        Limit your step by step plan to only these operations per step.
        Don't create more than 10 steps.

        Please ensure there's a README.md file in the root of the codebase that describes the codebase and how to run it.
        Please ensure there's a requirements.txt file in the root of the codebase that describes the dependencies of the codebase.

        Please output your plan in JSON format without any other content.

        Response:
        [
            "Create a file called main.py with the following content: 'print('Hello, World!')'",
            "Create a file called requirements.txt with the following content: ''",
            "Create a file called README.md with the following content: 'This is a codebase that prints 'Hello, World!'",
        ]

        
        Request:
        Create a step by step plan to complete the task of creating a codebase that will make an API call to google.com.
        You have 3 different operations you can perform. You can create a file, update a file, or delete a file.
        Limit your step by step plan to only these operations per step.
        Don't create more than 10 steps.

        Please ensure there's a README.md file in the root of the codebase that describes the codebase and how to run it.
        Please ensure there's a requirements.txt file in the root of the codebase that describes the dependencies of the codebase.

        Please output your plan in JSON format without any other content.

        Response:
        [
            "Create a file called main.py that uses the requests library to make an API call to google.com",
            "Create a file called requirements.txt with the following content: 'requests'",
            "Create a file called README.md with the following content: 'This is a codebase that makes an API call to google.com'",
        ]

        
        Request:
        Create a step by step plan to complete the task of creating a codebase that will {PROGRAM_OBJECTIVE}.
        You have 3 different operations you can perform. You can create a file, update a file, or delete a file.
        Limit your step by step plan to only these operations per step.
        Don't create more than 10 steps.

        Here is the codebase currently:
        {get_codebase_contents()}

        {prompt_feedback}
        Please ensure there's a README.md file in the root of the codebase that describes the codebase and how to run it.
        Please ensure there's a requirements.txt file in the root of the codebase that describes the dependencies of the codebase.

        """
    response = client.inference.chat_completion(
        model_id=MODEL_ID,
        messages=[
            {"role": "system", "content": CODER_AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        sampling_params={
            "max_tokens": MAX_TOKENS,
        },
        response_format={
            "type": "json_schema",
            "json_schema": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "Plan",
                "description": f"A plan to complete the task of creating a codebase that will {PROGRAM_OBJECTIVE}.",
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    }
                },
                "required": ["steps"],
                "additionalProperties": False,
            }
        },
    )
    try:
        content = response.completion_message.content
        content = content.replace("```json", "").replace("```", "")
        content = content.strip()
        plan = json.loads(content)
    except Exception as e:
        print(f"Error parsing plan into JSON: {e}")
        # If we don't get valid JSON, we'll just include the full plan
        plan = response.completion_message.content

    if isinstance(plan, dict):
        for step_idx, step in enumerate(plan["steps"]):
            print(f"{step_idx + 1}. {step}")
    else:
        print(plan)
    print("\n")

    # Coding agent executes the plan
    print(f"{BLUE}Coder Agent - Executing Plan - Iteration {i}{RESET}")
    if review_feedback:
        prompt_feedback = f"""
        Keep in mind one a senior engineer has provided the following feedback:
        {review_feedback}

        """
    else:
        prompt_feedback = ""

    if isinstance(plan, dict):
        for step in plan["steps"]:
            prompt = f"""
                You have 3 different operations you can perform. create_file(path, content), update_file(path, content), delete_file(path).
                Here is the codebase:
                {get_codebase_contents()}
                Please perform the following operation: {step}

                {prompt_feedback}
                Please don't create incomplete files.
                """
            try: 
                response = client.inference.chat_completion(
                    model_id=MODEL_ID,
                    messages=[
                        {"role": "system", "content": CODER_AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    sampling_params={
                        "max_tokens": MAX_TOKENS,
                    },
                    tools=TOOLS,
                    tool_prompt_format=tool_prompt_format,
                    # tool_choice="required",
                )
            except Exception as e:
                print(f"Error running tool - skipping: {e.message[:50] + '...'}")
                continue
            message = response.completion_message
            if message.content:
                print("Didn't get tool call - got message: ", message.content[:50] + "...")
            else:
                tool_call = message.tool_calls[0]
                run_tool(tool_call)
    else:
        # Do 5 iterations of the plan
        for _ in range(5):
            prompt = f"""
                You have 3 different operations you can perform. create_file(path, content), update_file(path, content), delete_file(path).
                Here is the codebase:
                {get_codebase_contents()}
                
                Please perform a part of the plan: {plan}

                {prompt_feedback}
                Please don't create incomplete files.
            """
            try: 
                response = client.inference.chat_completion(
                    model_id=MODEL_ID,
                    messages=[
                        {"role": "system", "content": CODER_AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    sampling_params={
                        "max_tokens": MAX_TOKENS,
                    },
                    tools=TOOLS,
                    tool_prompt_format=tool_prompt_format,
                    # tool_choice="required",
                )
            except Exception as e:
                print(f"Error running tool - skipping: {e.message[:50] + '...'}")
                continue
            message = response.completion_message
            if message.content:
                print("Didn't get tool call - got message: ", message.content[:50] + "...")
            else:
                tool_call = message.tool_calls[0]
                run_tool(tool_call)
    print("\n")

    print(f"{MAGENTA}Reviewer Agent - Reviewing Codebase - Iteration {i}{RESET}")
    response = client.inference.chat_completion(
        model_id=MODEL_ID,
        messages=[
            {"role": "system", "content": REVIEWER_AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": f"""
            Here is the full codebase:
            {get_codebase_contents()}
            Please review the codebase and make sure it is correct.
            Please provide a list of changes you would like to make to the codebase.
            """},
        ],
        sampling_params={
            "max_tokens": MAX_TOKENS,
        },
        stream=True,
    )
    review_feedback = ""
    for chunk in response:
        if chunk.event.delta:
            print(chunk.event.delta, end="", flush=True)
            review_feedback += chunk.event.delta
    print("\n")
