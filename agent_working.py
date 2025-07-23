import os
import traceback
import pymysql
from datetime import datetime
from rapidfuzz import process, fuzz
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import initialize_agent
from langchain.tools import Tool
from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL
from langchain.agents.agent_types import AgentType
from langchain.memory import ConversationBufferMemory

username = "root"
password = ""
host = "139.91.80.170" #host.docker.internal
port = 3306 
database = "berth_allocation_v2"

<<<<<<< HEAD
# api key in .env

=======
>>>>>>> c0ac93fa12217d682e3a6824f6e52182a612384c
connection_string = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"

max = 8000 # fixed

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Helper to fetch all ship names once
def fetch_all_ship_names():
    conn = pymysql.connect(host=host, user=username, password=password, db=database)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT title FROM vessel")
            return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()

ALL_SHIP_NAMES = fetch_all_ship_names()

@tool
def resolve_ship_name_tool(question: str) -> str:
    """
    Given a user question, returns the best matching ship name using fuzzy matching against known ships.
    Only returns a ship name if the fuzzy score is >= 70. Returns an empty string otherwise.
    """
    question_upper = question.upper()
    all_ships = ALL_SHIP_NAMES
    score_cutoff=70
    
    for ship in all_ships:
        if ship.upper() in question_upper:
            return ship, "exact match"
    
    # fuzzy match
    result = process.extractOne(
        query=question_upper,
        choices=all_ships,
        scorer=fuzz.token_set_ratio,
        score_cutoff=score_cutoff
    )

    if result is not None:
        best_match, score, _ = result
        return best_match, f"fuzzy match (score={score:.1f})"

    return ""

def get_mysql_agent_response(question: str, memory: ConversationBufferMemory):
    try:
        db = SQLDatabase.from_uri(connection_string)
        print("Connected.")

        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

        toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        
        sql_tools = toolkit.get_tools()
        
        calculator_tool = Tool(
            name="python_calculator",
            func=PythonREPL().run,
            description="Useful for answering questions that require simple math or calculations.",
        )
        
        tools = sql_tools + [calculator_tool] + [resolve_ship_name_tool]
        
        tool_names = ", ".join([tool.name for tool in tools])
        
        today = datetime.now().date()
        year = today.year
    
                
        prefix_temp = """
            You are an AI chatbot that answers requests about the schedule of cruise ships in Santorini.
            Your goal is to answer user questions using SQL queries, always in the form of natural conversation.
            
            **You must always return valid JSON fenced by a markdown code block. Do not return any additional text.**
            
            **ALWAYS keep track of the ongoing conversation context.** 
            **If the user asks a follow-up question, use the chat history to infer any missing details.**
            For example, if a cruise ship was previously discussed, and the user follows up without naming it, assume they are referring to the same ship.
            
            ** IMPORTANT: **
            [ After reaching the conclusion and writing:

            Thought: I now know the final answer.
            Final Answer: the final answer to the original input question
            You MUST STOP ! Do not generate more thoughts or actions. ]
            
            ## Database Schema:

            There are two relevant tables:

            ### Table: 'approach_request'. Its relevant columns include:
            - 'vessel_id': foreign key referencing 'vessel.id'
            - 'requested_start_date': stores ship arrival date
            - 'requested_end_date': date when approach ends
            - 'confirmed_approach': 1 if the approach is confirmed
            - 'approach_passengers': the actual approach number of passengers

            ### Table: 'vessel'. Its relevant columns include:
            - 'id': primary key
            - 'title': name of the cruise ship
            - 'capacity: the capacity of the ship
            
            To retrieve ship names or filter by ship name, you must join 'approach_request' and 'vessel' like this:
            ```sql
            JOIN vessel ON approach_request.vessel_id = vessel.id
            
            Do NOT reverse the join direction unless asked for ship metadata.
            
            - When users mention a ship name, ALWAYS use the 'resolve_ship_name_tool' to map the name to a known ship.
            - If the tool returns a ship name, AWLAYS ask the user first if that is the ship they are referring to, UNLESS the resolve_ship_name_tool EXPLICITLY returns 'exact match', so you can use that name in SQL queries.
                - If the user's answer confirms the ship name, use that name in SQL queries
                - Else, ask the user to give the ship name they want.
            - If the tool returns an empty string, inform the user the ship is not registered.
            
            ## When a user asks whether a specific cruise ship can be brought on a specific date, do the following:
                **If the date the user asked for is before '{today}' state clearly that that day has already passed.**
                1. **First, check if the ship name exists in the 'vessel' table.**
                        - If not found, respond clearly that the ship is not registered.
                2. **Get the ship's "capacity" from the "vessel" table using the ship name.**
                3. **Get the total sum of "approach_passengers" scheduled for the same date from the "approach_request" table.**
                4. **Use the fixed max passenger threshold: max=8000**
                
                ** Important: if the ship is ALREADY confirmed for that date (in the approach_request for that specific date), answer that it is already scheduled.**
                
            **Decision rules:**
                - If (max - total) > (0.8 * capacity), the answer is "Yes, the ship can be scheduled."
                - Else if (total + capacity) > (max + 800), the answer is "No, it cannot be scheduled."
                - Otherwise, respond with "Please refer to Port Management."
    
            **Important: Always use the python_calculator tool with the "print" function to evaluate the entire expression in a single call, for example like this:**
                - "print((8000 - 756) > (0.8 * 1582))"
                - "print((756 + 1582) > (8800))"
                
            **Only apply this logic if the user is asking whether a ship *can be scheduled* on a specific date (e.g. "Can we bring", "Is it possible to add", "Can we fit", etc).**
    
            **If the user is asking whether a ship *will be* on a date (e.g. "Will [ship] be here", "Is [ship] arriving", etc), simply check whether the ship is already scheduled for that date using the approach_request table, and skip all decision logic and capacity lookup.
            ALWAYS compare requested_start_date to the given date, using DATE(requested_start_date)**
            **If you CAN'T find the ship in the database IMMEDIATELY respond clearly that the ship is not registered.**
                    
            ## If the user asks which dates in a range (e.g., a month) a ship can be accepted:

                1. Consider ONLY the dates **after '{today}'** within that same range. 
                - For example, if today is the 17th of July, only consider July 18th onward.

                2. First, retrieve the ship's capacity from the `vessel` table using its name.

                3. Next, run **a single SQL query** to get the total `approach_passengers` for each existing date in that range from the `approach_request` table.
                    - ?? This query should return **only the dates that actually exist** in the database.
                    - If a date is **not present** in the result of the SQL query, it means **no ships are scheduled** for that day ? so assume **0 passengers** for that date.
                    - Do **not** generate separate queries per day. Do it in one SQL query.

                4. For each date:
                    - If it was returned by the SQL query ? use the `python_calculator` tool with a single expression:
                        - `print((8000 - total_passengers) > (0.8 * capacity))`
                    - If it was **not** returned ? assume the result is `"True"` (since 0 passengers), and do **not** use the calculator.

                5. Collect all dates that returned `"True"` from the logic above.

                6. If **all days** in the user's requested range are allowed, respond that the ship can be scheduled on **all dates**.
                Otherwise, list the acceptable dates.

                DO NOT run the same query repeatedly for each day.
                DO NOT query dates not returned by the SQL query.
                DO NOT use the calculator tool for days with 0 passengers, just assume "True".


            **You MUST evaluate these expressions using the "python_calculator" tool, NOT on your own.**
            **Your final answer should NOT include the calculations you made.**

            ## Core Rules:
            1.  **Always execute a SQL query** to get the answer. Do not rely on prior knowledge.
            2.  **Explicitly show the SQL query** you executed in a markdown block (```sql...```).
            3.  **Always use the requested_start_date column to filter based on date or date ranges**, regardless of what the user says.
            4.  **When comparing requested_start_date to a date, ALWAYS either use DATE(requested_start_date) or a time range like '2025-12-29 00:00:00' to '2025-12-30 00:00:00'**.
            5.  **When filtering by ship name, join the tables and filter on vessel.title using equality (vessel.title = 'Ship Name')** unless the user suggests a partial match.
            6.  **Provide the result directly and concisely.**.
            7.  **If the data doesn't exist, state so clearly and politely and apologize for not being able to answer**.
            8.  **Strictly NO data modification (INSERT, UPDATE, DELETE, DROP).** Only SELECT queries are allowed.
            9.  **After the SQL query, you must always print the returned rows clearly, even if there is only one result**. Do not say 'no ships' unless the result set is truly empty.
            10. **Assume "today" means '{today}'.**
            11. **If the user asks for a date like "5th September" without a year, assume the year is {year}.**
            12. **Always present the result in the form of natural conversation**.
            13. **Always check if the ship name the user gives exists in the 'vessel' table. If not found, respond clearly that the ship is not registered.**
            14. **Always look for confirmed_approach and ensure it's 1.** Ignore the ship if it's confirmed_approach is 0.
            

            **Always end your response with asking the user if they want further assistance.**
        


            Follow the schema and rules precisely.

            """
        
        prefix = prefix_temp.format(
            today=today,
            year=year,
        )
        
        format_instructions_temp = """
        
            Answer the following questions as best you can. You have access to the following tools:
            {tools}

            
            You MUST follow this strict format:

            Question: the input question you must answer
            Thought: you should always think about what to do
            Action: the action to take, should be one of [{tool_names}]
            Action Input: the input to the action
            Observation: the result of the action
            ... (this Thought/Action/Action Input/Observation can repeat N times)
            Thought: I now know the final answer
            Final Answer: the final answer to the original input question

            Begin!
            

            """
            
        
        format_instructions = format_instructions_temp.format(
            tools="\n".join([f"{tool.name}: {tool.description}" for tool in tools]),
            tool_names=tool_names
        )
        
        full_system_message = f"{prefix}\n\n{format_instructions}"
        
        executor = initialize_agent(
            agent = AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
            tools=tools,
            llm=llm,
            memory=memory,
            agent_kwargs={"system_message": full_system_message},
            verbose=True,
            max_iterations=30,
            handle_parsing_errors=True
        )
        

        print(f"\nAsking the agent: '{question}'")
            
        response = executor.invoke({"input": question})
        
        print("\n=== Chat History ===")
        for msg in memory.chat_memory.messages:
            if msg.type == "human":
                print(f"User: {msg.content}")
            elif msg.type == "ai":
                print(f"AI: {msg.content}")
            elif msg.type == "system":
                print(f"System: {msg.content}")
            else:
                print(f"{msg.type.capitalize()}: {msg.content}")
        print("====================\n")

        
        return response["output"]



    except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
        return "Could not retrieve data due to an error."
