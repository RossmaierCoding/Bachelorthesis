from langchain_core.messages import HumanMessage
from langchain_core.messages import AIMessage
from langchain_ollama import ChatOllama
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.runnables import RunnableLambda
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, START, END

from typing import TypedDict
import base64
from io import BytesIO
from PIL import Image
import asyncio
import tkinter as tk
from tkinter import filedialog
import re


class InputApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # Get Basic Tkinter Input Window
        self.title("Picture or Prompt")
        self.geometry("400x250")
        self.resizable(False, False)

        container = tk.Frame(self, padx=20, pady=20)
        container.pack(fill="both", expand=True)

        input_frame = tk.Frame(container)
        input_frame.pack(fill="x", pady=(0, 15))

        tk.Label(input_frame, text="Prompt:", width=12, anchor="w").grid(row=1, column=0, sticky="w", pady=5)
        self.entry = tk.Entry(input_frame)
        self.entry.grid(row=1, column=1, sticky="ew", padx=5)

        input_frame.columnconfigure(1, weight=1)

        file_frame = tk.Frame(container)
        file_frame.pack(fill="x", pady=(0, 15))

        tk.Button(file_frame, text="Picture", command=self.choose_file).pack(side="left")
        self.file_path = tk.StringVar()
        self.file_label = tk.Label(file_frame, textvariable=self.file_path, anchor="w")
        self.file_label.pack(side="left", padx=10, fill="x", expand=True)

        submit_btn = tk.Button(container, text="Submit", command=self.submit)
        submit_btn.pack(pady=10)

        # Initialize Variables
        self.user_input = None
        self.selected_file_path = None

    def choose_file(self):

        path = filedialog.askopenfilename(title="Choose a Picture")
        if path:
            self.file_path.set(path)

    def submit(self):

        self.user_input = str(self.entry.get())

        self.selected_file_path = str(self.file_path.get())

        # Close The Window After Submit
        self.destroy()


class MyState(TypedDict):

    # Pass States Through Stategraph
    vision: str
    code: str
    plan: str
    filepath: str
    userinput: str

def prompt_func(data):

    # Chain Image And Text Data
    text = data["text"]
    image = data["image"]

    image_part = {
        "type": "image_url",
        "image_url": f"data:image/png;base64,{image}",
    }

    content_parts = []

    text_part = {"type": "text", "text": text}

    content_parts.append(image_part)
    content_parts.append(text_part)

    return [HumanMessage(content=content_parts)]


def convert_to_base64(pil_image):

    # Convert PIL Images To Base64 Encoded Strings
    buffered = BytesIO()
    pil_image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str


async def vision_llm_func(state: MyState) -> MyState:

    # Get Image Data
    file_path = state["filepath"]
    if file_path == "":
        # Create Vision Agent Chain
        vision_llm_chat = ChatOllama(
            model="llama4:maverick",
            base_url="http://localhost:11434",
            temperature=0.5,
        )

        # Get Agent Result
        prompt = """You are an expert in image analysis, 3D modeling, and Blender scripting. 
            Provide a detailed and extensive description of the scene and list all assets including hdri, models and textures you will need to create it."""+state["userinput"]
        vision_result = vision_llm_chat.invoke(prompt)

        # Ouput Image LLM
        print("\n")
        print("ImageLLM Output:")
        print("\n")
        print(vision_result.content)
        print("\n")

        state["vision"] = vision_result.content
        return state
    
    try:

        pil_image = Image.open(file_path)

    except Exception as e:
        print(f"Error in main execution: {e}")


    image_b64= convert_to_base64(pil_image)

    # Create Vision Agent Chain
    vision_llm_chat = ChatOllama(
        model="llama4:maverick",
        temperature=0.9,
    )

    prompt_func_runnable = RunnableLambda(prompt_func)
    chain = prompt_func_runnable | vision_llm_chat

    prompt_vision = """You are an expert in image analysis, 3D modeling, and Blender scripting. 
        Provide a detailed and extensive description of the image and list all assets including hdri, models and textures you will need to create it."""

    # Get Agent Chain Result
    vision_result = chain.invoke({
        "text": prompt_vision,
        "image": image_b64,
    })

    print("\n")
    print("ImageLLM Output:")
    print("\n")
    print(vision_result.content)
    print("\n")

    state["vision"] = vision_result.content

    return state

async def vision_llm_func_feedback(state: MyState) -> MyState:

    # Get Image Data
    file_path = state["filepath"]
    
    try:

        pil_image = Image.open(file_path)

    except Exception as e:
        print(f"Error in main execution: {e}")


    image_b64= convert_to_base64(pil_image)

    # Create Vision Agent Chain
    vision_llm_chat = ChatOllama(
        model="llama4:maverick",
        temperature=0.9,
    )

    prompt_func_runnable = RunnableLambda(prompt_func)
    chain = prompt_func_runnable | vision_llm_chat

    prompt_vision_loop = """You are an expert in image analysis, 3D modeling, and Blender scripting. 
            Provide a detailed comparison of the image and the discription.
            Mark out all the differences.
            """+state["vision"]
    # Get Agent Chain Result
    vision_result = chain.invoke({
        "text": prompt_vision_loop,
        "image": image_b64,
    })

    print("\n")
    print("ImageLLM Output:")
    print("\n")
    print(vision_result.content)
    print("\n")

    state["vision"] = vision_result.content

    return state

async def plan_llm_func(state):

    # Create Plan Agent
    plan_llm_chat = ChatOllama(
        model="llama4:maverick",
        temperature=0.0,
    )


    # Create Plan
    prompt = """You are tasked with constructing a relational bipartite graph for 3D Scene based on the provided description and assetlist.
        1.Review the Scene description and the list of assets.
        2.Determine the spatial and contextual relionships needed to accurateley represent the scene's layout. Consider Relationships like:
        -Proximity: A constraint enforcing the closeness of two objects, e.g., a chair near a table.
        -Direction: The angle of one object is targeting at the other.
        -Alignment: Ensuring objects align along a common axis, e.g., paintings aligned vertically on a wall.
        -Symmetry: Mirroring objects along an axis, e.g., symmetrical placement of lamps on either side of a bed.
        -Overlap: One object partially covering another, creating depth, e.g., a rug under a coffee table.
        -Parallelism: Objects parallel to each other, suggesting direction, e.g., parallel rows of seats in a theater.
        -Perpendicularity: Objects intersecting at a right angle, e.g., a bookshelf perpendicular to a desk.
        -Hierarchy: Indicating a list of objects follow a certain order of size / volumns.
        -Rotation: a list of objects rotate a cirtain point, e.g., rotating chairs around a meeting table.
        -Repetition: Repeating patterns for rhythm or emphasis, e.g., a sequence oft street lights.
        -Scaling: Adjusting object sizes for depth or focus, e.g., smaller background trees to create depth perception
        Construct the relational bipartite graph 'G(s)=(A,R,E)' where:
        -A represents the set of assets.
        -R represents the set of Relations as nodes.
        -E represents the edges connecting a relation node to a subset of assets 'E(r)' in the Scene that satisfies this relation.
        Output your findings in a structured Format:
        List of relation nodes 'R' with their types and descriptions.
        Edges 'E' that link assests to their corresponding relation nodes.
        This process will guide the Arrangement of assets in the 3D Scene, ensuring they are positioned scaled and oriented correctly according to the description.
        """+state["vision"]

    plan = plan_llm_chat.invoke(prompt)
    filtered_plan = re.sub(r'<think>.*?</think>\s*', '', plan.content, flags=re.DOTALL)

    # Output PlanLLM
    print("\n")
    print("PlanLLM Output:")
    print("\n")
    print(filtered_plan)
    print("\n")

    state["plan"] = filtered_plan
    return state

def code_llm_func(state):

    # Create Code Agent
    code_llm_chat = ChatOllama(
        model="llama4:maverick",
        temperature=0.9,
    )


    # Get Agent Result
    prompt_code = """You are an expert in image analysis, 3D modeling, and Blender scripting. 
            Implement the provided graph to create the described Landscape in Blender."""
    code_llm_chat_input = state["plan"]+"\n"+prompt_code
    code_result = code_llm_chat.invoke(code_llm_chat_input)

    print("\n")
    print("CodeLLM Output:")
    print("\n")
    print(code_result.content)
    print("\n")
    state["code"] = code_result.content

    return state

def code_llm_func_feedback(state):

    # Create Code Agent
    code_llm_chat = ChatOllama(
        model="qwen3:235b",
        temperature=0.9,
    )


    # Get Agent Result
    prompt_code = """You are an expert in image analysis, 3D modeling, and Blender scripting. 
            Implement the provided graph to create the described Landscape in Blender.
            Furthermore try to minimize the following differences"""
    code_llm_chat_input = state["plan"]+"\n"+prompt_code+state["vision"]
    code_result = code_llm_chat.invoke(code_llm_chat_input)

    print("\n")
    print("CodeLLM Output:")
    print("\n")
    print(code_result.content)
    print("\n")
    state["code"] = code_result.content

    return state


async def tools_llm_func(state):

    # Get MCP-Tools From Server
    client = MultiServerMCPClient(
        {
            "blender_mcp": {
                "command": "uvx",
                "args": ["blender-mcp"],
                "transport": "stdio",
            }
        }
    )
    try:

        tools = await client.get_tools()

    except Exception as e:
        print(f"Error in main execution: {e}")

    # Filter The Tools
    filtered_tools = [t for t in tools if t.name not in {"get_hyper3d_status", "get_sketchfab_status", "search_sketchfab_models","download_sketchfab_models","generate_hyper3d_model_via_text","generate_hyper3d_model_via_images","poll_rodin_job_status","import_generated_asset"}]
    
    # Create Llm Chat
    tools_llm_chat = ChatOllama(
        model="qwen3:235b",
        temperature=0.0,
    )
    
    #Create Tool Agent
    agent = create_react_agent(
        model = tools_llm_chat,
        tools=filtered_tools
    )


    # Get Agent Result
    try:
        tool_result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "You are an expert in image analysis, 3D modeling, and Blender scripting."+
            "\nImport all assets you need to execute the script from Polyhaven.\n"+state["code"]+
            "\nExecute the following Blender Python Code:\n"+state["code"]+
            "\nIf it does not work try to correct the code and reexecute"              
            }]}
        )

    except Exception as e:
        print(f"Error in main execution: {e}")

    ai_messages = [m for m in tool_result["messages"] if isinstance(m, AIMessage)]
    full_output = "\n\n".join(m.content for m in ai_messages)
    filtered_output = re.sub(r'<think>.*?</think>\s*', '', full_output, flags=re.DOTALL)

    # Make Viewport Screenshot
    screenshot_code = """
        import bpy

        # Create a new camera object
        cam_data = bpy.data.cameras.new(name="MyCamera")
        cam_object = bpy.data.objects.new("MyCamera", cam_data)

        # Set camera location and rotation
        cam_object.location = (0, -10, 7)
        cam_object.rotation_euler = (1.1, 0, 0)

        # Link the camera to the current scene
        bpy.context.collection.objects.link(cam_object)

        # Set the new camera as the active camera
        bpy.context.scene.camera = cam_object

        bpy.context.scene.render.filepath = "C:\\Users\\cross\\Desktop\\Render.png"
        bpy.ops.render.render(write_still=True)

        """
    try:
        tool_result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "Execute the following Blender Python Code:\n"+screenshot_code+
            "\nIf it does not work try to fix and reexecute it."}]}
        )
        print("\n")
        print("ToolLLM Output:")
        print("\n")
        print("Screenshot taken.")
        print("\n")
    except Exception as e:
        print(f"Error in main execution: {e}")

    # Get Code Agent Result
    print("\n")
    print("CodeLLM Output:")
    print("\n")
    print(filtered_output)
    print("\n")

    return state


async def main():

    # Open Input Window
    app = InputApp()
    app.mainloop()

    # Output Collected Inputs In Terminal
    print("Inputs collected:")
    print("llm_prompt =", app.user_input)
    print("selected_file_path =", app.selected_file_path)
    file_path = app.selected_file_path
    user_input = app.user_input

    # Loop Until At Least One Input Collected
    while file_path == "" and user_input == "":
        app = InputApp()
        app.mainloop()
        print("Inputs collected:")
        print("llm_prompt =", app.user_input)
        print("selected_file_path =", app.selected_file_path)
        file_path = app.selected_file_path
        user_input = app.user_input


    # Create StateGraph With Nodes And Edges
    graph = StateGraph(MyState)
    graph.add_node("vision_llm", vision_llm_func)
    graph.add_node("code_llm", code_llm_func)
    graph.add_node("plan_llm",plan_llm_func)
    graph.add_node("tools_llm", tools_llm_func)
    graph.add_edge(START,"vision_llm")
    graph.add_edge("vision_llm", "plan_llm")
    graph.add_edge("plan_llm","code_llm")
    graph.add_edge("code_llm", "tools_llm")
    graph.add_edge("tools_llm",END)
    graph = graph.compile()

    # Get StateGraph Output State
    input_state = MyState(userinput=user_input,filepath=file_path)
    output_state = await graph.ainvoke(input_state, config={"recursion_limit": 150})

    # Create StateGraph With Nodes And Edges for Feedback Loop
    graph = StateGraph(MyState)
    graph.add_node("vision_llm", vision_llm_func_feedback)
    graph.add_node("code_llm", code_llm_func_feedback)
    graph.add_node("tools_llm", tools_llm_func)
    graph.add_edge(START,"vision_llm")
    graph.add_edge("vision_llm", "code_llm")
    graph.add_edge("code_llm", "tools_llm")
    graph.add_edge("tools_llm",END)
    graph = graph.compile()

    # Prepare Rendering Loop
    file_path_loop = "C:\\Users\\cross\\Desktop\\Render.png"
    output_state["filepath"] = file_path_loop
    input_state = output_state
    
    # Start Feedback Loop
    for i in range(4):
        print("\n")
        print(f"++++++++++++++++++++++++++++++")
        print(f"+ Feedback Loop iteration: {str(i+2)} +")
        print(f"++++++++++++++++++++++++++++++")
        print("\n")
        output_state = await graph.ainvoke(input_state, config={"recursion_limit": 150})
        input_state = output_state


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())
    
