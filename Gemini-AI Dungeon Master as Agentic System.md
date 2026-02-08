# AI Dungeon Master as Agentic System

**Exported:** 2/7/2026 18:24:48  
**Link:** [https://gemini.google.com/app/e8e25e888d5519a7?android-min-version=301356232&ios-min-version=322.0&is_sa=1&campaign_id=gemini_overview_page&utm_source=gemini&utm_medium=web&utm_campaign=microsite_gemini_image_generation_page&pt=9008&mt=8&ct=gemini_overview_page&hl=en-US&icid=microsite_gemini_image_generation_page](https://gemini.google.com/app/e8e25e888d5519a7?android-min-version=301356232&ios-min-version=322.0&is_sa=1&campaign_id=gemini_overview_page&utm_source=gemini&utm_medium=web&utm_campaign=microsite_gemini_image_generation_page&pt=9008&mt=8&ct=gemini_overview_page&hl=en-US&icid=microsite_gemini_image_generation_page)

## Prompt:
Conceptualize a AI dungeon master in the world of DnD (or better configurable background story), that operate similar to claude code, but for game. What would that system look like?

## Response:
A "Claude Code for D&D" system would function as an **autonomous, agentic CLI (Command Line Interface) Dungeon Master**.

Unlike standard AI DMs (which are essentially chat bots that hallucinate rules), this system—let’s call it **"DungeonOS"**—would operate exactly like an engineer’s agent. It would have read/write access to a "file system" of lore, a "terminal" for executing rigid game mechanics, and an "agent loop" to reason through complex narrative arcs.

Here is the conceptual architecture of that system.

* * *

### 1\. The Core Philosophy: "Agentic" vs. "Chat"

*   **Chat DM (Current State):** You type "I hit the goblin." The AI guesses the AC, guesses the damage, and writes a description. It often forgets the goblin’s health 10 turns later.
*   **Agentic DM (DungeonOS):** You type "I hit the goblin." The Agent:
    1.  **Reads** the `goblin_01.json` file to check current HP and AC.
    2.  **Executes** a dice roll script `roll(d20 + 5)` in its internal terminal.
    3.  **Compares** the result to the AC.
    4.  **Writes** the damage to `goblin_01.json`.
    5.  **Generates** the narrative description based on the _confirmed_ state change.

### 2\. The Architecture

The system mimics a coding agent environment but replaces software concepts with RPG concepts.

| Claude Code Feature | DungeonOS Equivalent | Function |
| --- | --- | --- |
| **File System** | **The World State** | A structured folder of `.md` (lore) and `.json` (stats) files representing the campaign. |
| **Terminal / Shell** | **The Rule Engine** | A Python/JavaScript runtime that executes hard rules (combat math, skill checks, inventory logic). |
| **Context Window** | **The Scene Cache** | A running buffer of the immediate situation, loaded from the World State. |
| **Agent Loop** | **The Dungeon Master** | The LLM that plans, retrieves files, executes rule scripts, and narrates the result. |

### 3\. Key Components

#### A. The "Repository" (Configurable Background)

Instead of a code repository, you initialize the game in a folder. The background story is fully configurable because it is just text files.

*   `/world/lore/`: Markdown files describing history, factions, and geography.
*   `/world/npcs/`: Character sheets in JSON format (e.g., `strahd.json`).
*   `/session_logs/`: Auto-generated transcripts of previous sessions.
*   `config.yaml`: The "settings" file defining the genre (Fantasy, Sci-Fi), rule set (5e, Pathfinder), and tone (Gritty, High Fantasy).

#### B. The Interface (CLI)

The user interacts via a terminal interface, identical to Claude Code.

```
> dungeon -i "I want to sneak up on the guard and pickpocket his key."
```

#### C. The Agent Loop

When you enter a command, the system performs a **ReAct (Reason + Act)** loop:

1.  **Thought:** "User wants to sneak. I need the guard's Passive Perception from `guard_02.json` and the player's Stealth modifier from `player.json`."
2.  **Action:** `read_file("world/npcs/guard_02.json")`
3.  **Action:** `execute_script("check_stealth.py", player_mod=5, difficulty=12)`
4.  **Observation:** "Roll: 18. Success."
5.  **Action:** `update_file("world/player/inventory.json", add="Iron Key")`
6.  **Response:** "You slip into the shadows... (narrative description) ... You feel the cold metal of the key in your hand."

### 4\. Advanced "Claude Code" Features Adapted

#### "Grep" for Lore (RAG)

Just as Claude Code searches a codebase for definitions, DungeonOS searches your lore files.

*   **User:** "Who is the king of this city again?"
*   **System:** Scans `/world/lore/*.md`  $\to$  Finds `city_politics.md`  $\to$  "King Alaric III, known as the Iron-Handed."

#### "Refactoring" (World Evolution)

If the players kill a major villain or burn down a town, the Agent doesn't just remember it in chat history; it **edits the files**.

*   _Action:_ The agent opens `town_map.md` and changes the description from "bustling market" to "smoldering ruins."
*   _Consequence:_ If you return 5 sessions later, the agent reads the _updated_ file and describes the ruins accurately.

#### "Test Suite" (Encounter Balance)

Before an encounter starts, the agent can run a simulation to see if it's too hard.

*   _Internal Thought:_ "Running combat simulation... Party wipe probability 85%. Too high. Adjusting `bandit_count` from 10 to 6."

### 5\. Example Workflow

**User:** `> init -campaign "Cyberpunk Heist" -tone "Noir"`

**DungeonOS:**

> initializing campaign... generated /world/factions/megacorps.md generated /world/npcs/fixer.json Campaign ready. You stand in the rain outside the Neon Lotus club.

**User:** `> /check perception "Do I see anyone following me?"`

**DungeonOS (Internal Logs):**

*   `read_state(location="Neon Lotus")`
*   `roll_dice(d20 + wisdom_mod)` -\> Result: 4 (Fail)
*   `query_plot("is_player_followed")` -\> True (Assassin hidden)

**DungeonOS (Output):**

> You glance over your shoulder, but the neon rain makes it hard to see. The street looks empty. (Hidden State: The assassin moves closer.)

### 6\. Why this is "Better"

1.  **True Permanence:** Unlike ChatGPT, which eventually forgets the name of the NPC you met 300 messages ago, this system stores that NPC in a file. It never forgets.
2.  **Configurability:** You can fork a campaign like a GitHub repo. "Here is my `Curse of Strahd` repo—it has all the files pre-set."
3.  **No Math Errors:** The LLM doesn't do the math; it writes code to do the math.

### Next Step

Would you like me to generate a **folder structure and a `config.json` example** for a specific setting (e.g., High Fantasy or Space Opera) to demonstrate how the "file system" aspect would work?

## Prompt:
Should we build this from scratch or can we use open code or something as base

## Response:
This is the classic "Build vs. Buy" engineering dilemma.

**Bottom Line:** **Do not build this from 100% scratch.** The "plumbing" of an agent (reading files, calling tools, maintaining memory) is complex and solved by existing open-source tools.

I recommend a **Hybrid Approach**: Use a "Coding Agent" framework as your engine, but feed it RPG data instead of software code.

Here are your three best paths, ranked from "easiest/coolest" to "hardest/custom."

* * *

### Path 1: The "Hacker" Move (Repurpose a Coding Agent)

**Recommended for:** Immediate gratification and staying true to the "Claude Code" feel.

Since a D&D campaign is just a file system of text (Lore) and logic (Stats), **you can literally use an open-source coding agent as your DM right now.** You don't need a game engine; you need a text-editing engine.

*   **The Tool:** **
    [Aider](https://github.com/aider-ai/aider)
    ** (CLI) or **
    [Cline](https://github.com/cline/cline)
    ** (VS Code).
*   **Why it works:** These tools are built to read a file structure, understand context, and make edits.
*   **How to do it:**
    1.  Install Aider.
    2.  Create a folder `MyCampaign`.
    3.  Create a file `CONVENTIONS.md` (System Prompt): _"You are a Dungeon Master. Do not write code. When I speak, update the story logs. When I attack, run a Python script to calculate damage and update the enemy's JSON file."_
    4.  Run `aider --model gpt-4o` (or Claude 3.5 Sonnet).
    5.  **Result:** You now have a CLI agent that has "read/write" access to your entire campaign world.

### Path 2: The "Game-Specific" Base (Fork an Existing Project)

**Recommended for:** If you want a GUI, maps, or visual assets out of the box.

There are existing open-source projects attempting exactly this. Forking one gives you a head start on the UI, even if you replace the "Brain" later.

*   **
    [DungeonLM](https://github.com/UTSAVS26/DungeonLM)
    :** A Python/Streamlit based agent. It already has logic for inventory, ASCII maps, and turn-based combat.
*   **
    [Dungeo\_ai\_GUI](https://github.com/Laszlobeer/Dungeo_ai_GUI)
    :** A local, GUI-based DM designed to run with local models (Ollama). It’s modular and designed for solo-play.
*   **
    [AI-Dungeon-Master (Voiceflow Templates):](https://www.voiceflow.com/blog/ai-dungeon-master)
    ** If you prefer a "drag-and-drop" logic flow rather than code, Voiceflow has templates for RPG logic that connect to LLMs.

### Path 3: The "Framework" Build (Build using Orchestration Tools)

**Recommended for:** If you want to create a robust product or a highly complex system with specific rule enforcement (e.g., rigid Pathfinder 2e rules).

If you build, **start with an Agent Framework**, not raw Python. You want a library that handles "Tool Calling" (executing dice rolls) and "Memory" (RAG).

*   **The Stack:**
    *   **Brain:** **
        [LangGraph](https://langchain-ai.github.io/langgraph/)
        ** (Python). This is critical. Unlike standard LangChain, LangGraph handles _cycles_ (loops), which is essential for a game loop (Player Turn -\> DM Turn -\> Check State -\> Repeat).
    *   **Memory:** **
        [ChromaDB](https://www.trychroma.com/)
        ** (Local Vector Store). Use this to store thousands of lore snippets and retrieve only relevant ones ("Who is the King?") via RAG.
    *   **Architecture:**
        1.  **Router Agent:** Decides if the user input is "Talk", "Combat", or "Inventory".
        2.  **Rule Agent:** Has access to a Python REPL to execute math.
        3.  **Narrator Agent:** Writes the final output.

### Summary Comparison

| Feature | Path 1: Repurpose Aider/Cline | Path 2: Fork DungeonLM | Path 3: Build w/ LangGraph |
| --- | --- | --- | --- |
| **Setup Time** | 10 Minutes | 1 Hour | 2 Weeks |
| **UI** | Terminal / VS Code | Streamlit / Web | Custom |
| **Flexibility** | Extreme (It's just files) | Low (Hardcoded logic) | High (You build it) |
| **"Feel"** | Like `claude code` | Like a Video Game | Like a SaaS App |

**My Suggestion:** Start with **Path 1 (Aider)**. It costs nothing but an API key to test the _concept_. If you find yourself frustrated by the lack of structured state (like HP tracking getting messy), then graduate to **Path 3** using LangGraph to formalize those specific mechanics.

Would you like me to write the `CONVENTIONS.md` or `system_prompt.md` file you would need to drop into **Aider** to turn it into a Dungeon Master immediately?

## Prompt:
If I repurpose aider or open code, how would I include specific tool such as rolling dice etc?

## Response:
This is the key to making the system work. Since tools like **Aider** or **OpenHands (formerly OpenDevin)** are designed to "write code" and "run terminal commands," you don't need to build a complex plugin system.

You simply **give them a script of tools** (like `dungeon_tools.py`) and instruct them to **run that script** whenever they need to resolve an action.

Here is the exact workflow to repurpose Aider/OpenHands into a rules-hardened DM.

### 1\. The "Toolbox" File

Create a file in your project root called `dm_tools.py`. This contains the "Rigid Logic" you don't want the AI to hallucinate.

```
# dm_tools.py
import random
import json
import sys

def roll(dice_str):
    """
    Parses '2d6+4' or '1d20' and returns the result.
    Usage: python dm_tools.py roll 1d20+5
    """
    try:
        parts = dice_str.lower().split('+')
        modifier = int(parts[1]) if len(parts) > 1 else 0
        d_part = parts[0].split('d')
        count = int(d_part[0]) if d_part[0] else 1
        sides = int(d_part[1])
        
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + modifier
        
        output = {
            "formula": dice_str,
            "rolls": rolls,
            "modifier": modifier,
            "total": total
        }
        print(json.dumps(output, indent=2))
    except Exception as e:
        print(f"Error parsing dice: {e}")

def check_skill(skill_mod, dc):
    """
    Runs a d20 skill check.
    Usage: python dm_tools.py check 5 12
    """
    d20 = random.randint(1, 20)
    total = d20 + int(skill_mod)
    result = "SUCCESS" if total >= int(dc) else "FAILURE"
    
    print(json.dumps({
        "roll": d20,
        "modifier": skill_mod,
        "total": total,
        "dc": dc,
        "result": result
    }, indent=2))

if __name__ == "__main__":
    # Simple CLI router
    command = sys.argv[1]
    args = sys.argv[2:]
    
    if command == "roll":
        roll(args[0])
    elif command == "check":
        check_skill(args[0], args[1])
```

### 2\. The "System Instruction" (The Glue)

Now, you need to tell Aider how to behave. You do this via a `CONVENTIONS.md` file (which Aider automatically reads) or by pasting this into the chat at the start.

**File:** `CONVENTIONS.md`

> **ROLE:** You are the Dungeon Master (DM) for a D&D campaign running in this folder.
> 
> **CRITICAL RULE:** Do not guess math. Do not hallucinate dice rolls.
> 
> **HOW TO RESOLVE ACTIONS:**
> 
> 1.  **Identify the mechanic:** If the user says "I attack", identify the weapon damage (e.g., "1d8+3") from `character_sheet.json`.
> 2.  **Execute the Tool:** Run the command in the terminal: `python dm_tools.py roll 1d8+3`.
> 3.  **Read the Output:** Look at the JSON output from the terminal.
> 4.  **Narrate:** Use the _actual_ number generated by the script to write your response.
>     
> 
> **STATE MANAGEMENT:**
> 
> *   If an NPC takes damage, you MUST edit their file (e.g., `world/npcs/goblin.json`) to lower their HP.
> *   Never just "remember" HP in the chat. Write it to disk.
>     

### 3\. The User Experience (How it looks in action)

You are now in your terminal running Aider.

**User:** `> I swing my longsword at the goblin.`

**Aider (Thinking/Acting):**

1.  _Reads `character_sheet.json` to find Longsword = +5 to hit, 1d8+3 damage._
2.  _Reads `goblin.json` to find AC = 15._
3.  _Runs command:_ `python dm_tools.py roll 1d20+5`
4.  _Output:_ `{"total": 18}` (Hit!)
5.  _Runs command:_ `python dm_tools.py roll 1d8+3`
6.  _Output:_ `{"total": 7}`
7.  _Edits `goblin.json`: changes `hp: 7` to `hp: 0`._

**Aider (Final Response):**

> You lunge forward. The die clatters... **(Rolled 18 vs AC 15)**. A solid hit! You deal **7 damage**, piercing the goblin's leather armor. It gasps one last time and collapses. I have updated the goblin's status to "Dead".

### Why this is powerful

You are leveraging the Agent's ability to **use the CLI**.

*   **Inventory:** You can have a script `python dm_tools.py give_item "Potion" "Player"` that handles the JSON manipulation safely so the LLM doesn't corrupt the file.
*   **Random Encounters:** `python dm_tools.py random_encounter forest` could return a random monster from a CSV file.

### Next Step

Would you like me to create the **full `dm_tools.py` script** with support for Combat (Attacks vs AC) and HP tracking, so you can copy-paste it and start playing?

## Prompt:
Is it necessary to promote these to actual "tool" for tool use for the agentic code?

## Response:
No, it is **not necessary**, and for your specific use case (repurposing a coding agent like Aider or OpenHands), it is actually **better to avoid formal "Tool Use" definitions.**

Here is the distinction and why the "Script" approach is superior for this specific architecture.

### 1\. The Distinction: "Formal Tools" vs. "CLI Execution"

*   **Formal "Tool Use" (Function Calling):** This is the standard OpenAI/Anthropic API approach. You must define a JSON schema for every function (e.g., `roll_dice(sides: int)`). The LLM returns a structured object, your backend intercepts it, executes the code, and feeds it back.
    *   _Pro:_ Highly structured.
    *   _Con:_ Rigid. You have to rebuild/restart your backend every time you want to add a new "spell" or mechanic.
*   **CLI Execution (The Aider/Claude Code Approach):** This is the "Human Simulation" approach. The Agent has permission to access the terminal. To the Agent, your `dm_tools.py` is just another utility like `git` or `ls`.
    *   _Pro:_ **Zero-Setup Extensibility.** If you want to add a new "Random Loot" generator mid-game, you just write `loot.py`. You don't need to restart the agent or update an API schema. The agent sees the new file and can run it immediately.

### 2\. Why CLI Execution is Better for a D&D Agent

If you are using Aider/OpenHands, the "Terminal" **is** the Tool.

#### A. Hot-Swappable Mechanics

In D&D, you often invent rules on the fly ("homebrew").

*   **With Formal Tools:** You’d have to stop the server, code a new function `roll_sanity_check()`, add the JSON schema, and restart.
*   **With CLI Scripts:** You tell the Agent: _"Create a script `sanity.py` that rolls d100 and fails if the result is \> 80."_ The Agent **writes the tool itself** and then immediately uses it.

#### B. The "Unix Philosophy"

You can chain commands just like a developer.

> _"Roll for initiative for all 5 goblins and sort them."_

*   **Formal Tool:** You'd need a complex function `roll_group_initiative(count, modifier)`.
*   **CLI Agent:** It can just run a loop or use standard shell tricks: `for i in {1..5}; do python dm_tools.py roll 1d20+2; done`

### 3\. How to Make it Reliable (The "Soft" Tool Definition)

Since you aren't using strict JSON schemas, you need to prevent the Agent from "holding it wrong." You do this by making your scripts output **JSON** to the terminal (stdout).

The Agent reads the terminal output. If the output is English text, the Agent might misinterpret it. If it is JSON, the Agent understands it perfectly.

**Do this in your script:**

```
# GOOD: The Agent can parse this reliably
print(json.dumps({
    "action": "attack",
    "roll": 18,
    "hit": True,
    "damage": 6
}))
```

**Avoid this:**

```
# BAD: The Agent might get confused by flavor text
print("You rolled an 18 which is pretty good so yeah you hit for 6 damage.")
```

### 4\. Summary

**Don't promote them to API Tools.**

Just create a folder called `/bin` or `/scripts` in your campaign directory. Put your logic there. Tell the Agent in your `CONVENTIONS.md`:

> "I have provided utility scripts in the `/scripts` folder. Whenever you need to determine an outcome, check if a script exists for it and execute it via the terminal. Always prefer running code over guessing."

This turns your Agent into a **SysAdmin for your Fantasy World**, which is exactly the vibe you want for a "Claude Code" style DM.

## Prompt:
So this repo will be a initial setup. How would we manage advantures individually? Like saving the storyline, character and items etc, to continue playing a previous story or start a new one.

## Response:
You need to treat your repository like a **Game Engine (The Code)** vs. **Save Files (The Data)**.

Since you are using a file-based agent (like Aider/Cline), the "Folder Structure" **is** the architecture. If you organize the folders correctly, the Agent will naturally "load" the right memory and "save" to the right place.

Here is the blueprint for a **Multi-Campaign Repository**.

### 1\. The Repository Structure

This structure separates the "System" (Tools/Rules) from the "Saves" (Campaigns).

```
/my-dungeon-os
├── /system              <-- THE ENGINE (Shared across all games)
│   ├── dm_tools.py      # The dice roller/inventory scripts
│   ├── rules_5e.md      # Reference for D&D 5e rules
│   └── CONVENTIONS.md   # The System Prompt for the Agent
│
├── /library             <-- THE ASSETS (Static Data)
│   ├── /monsters        # json files (goblin.json, dragon.json)
│   ├── /items           # json files (sword.json, potion.json)
│   └── /classes         # json files (wizard.json, rogue.json)
│
├── /campaigns           <-- THE SAVE SLOTS
│   ├── /campaign_01_misty_peaks
│   │   ├── /characters  # The party's sheets
│   │   ├── /world       # Local maps and NPC states
│   │   ├── session_log.md  # The active chat history
│   │   └── state.json   # The "Current Save" (Time, Location, Active Quest)
│   │
│   └── /campaign_02_cyber_heist
│       ├── ...
│
└── active_session.json  <-- POINTER FILE
```

* * *

### 2\. The "Pointer" File (`active_session.json`)

To switch adventures, you don't need to move files around. You just update this tiny configuration file in the root. The Agent reads this first to know "Who am I today?"

```
{
  "current_campaign": "campaigns/campaign_01_misty_peaks",
  "last_played": "2023-10-27",
  "mode": "play" 
}
```

**User Command:** "Switch to the Cyber Heist campaign." **Agent Action:** Updates `current_campaign` path in this file.

* * *

### 3\. How to Manage "State" (Saving the Game)

In a video game, RAM holds the current state. In this system, a `state.json` file inside the campaign folder holds it.

**File:** `campaigns/campaign_01_misty_peaks/state.json`

```
{
  "game_time": "Day 4, 14:00 PM",
  "location": "The Prancing Pony Inn",
  "weather": "Rainy",
  "active_encounter": null,
  "quest_log": [
    {"id": 1, "title": "Find the Blacksmith", "status": "active"},
    {"id": 2, "title": "Kill Rats", "status": "completed"}
  ],
  "party_status": "Resting"
}
```

**Why this matters:** When you resume the game 3 weeks later, the Agent reads this file and immediately knows: _"It is raining, we are at the Inn, and we need to find the Blacksmith."_ It doesn't need to re-read 5,000 lines of chat history.

* * *

### 4\. Workflow: Starting & Switching

#### A. Starting a New Adventure (The "New Game" Button)

You don't want to create folders manually. You ask the Agent to do it.

**User:** `> Initialize a new campaign called "Space Odyssey". Use a Sci-Fi tone.`

**Agent Actions (Internal):**

1.  Creates folder `campaigns/space_odyssey`.
2.  Copies a "template" structure (folders for chars/world).
3.  Creates `state.json` initialized to "Day 1".
4.  Updates `active_session.json` to point to this new folder.
5.  **Output:** "Campaign 'Space Odyssey' initialized. Character creation enabled."

#### B. The "Context Flush" (The "Save & Quit" Button)

LLM context windows get full. If you play for 4 hours, the chat gets too long. You need a "End of Session" protocol.

**User:** `> Wrap up the session.`

**Agent Actions (Internal):**

1.  **Summarize:** Reads the recent `session_log.md`.
2.  **Update Lore:** If you met an NPC, creates `world/npc_gandalf.json`.
3.  **Update State:** Updates `state.json` with new location/health.
4.  **Archive:** Moves the raw text of the session to `archives/session_01.md`.
5.  **Clear:** Wipes `session_log.md` clean for next time.
6.  **Output:** "Session saved. See you next time."

* * *

### 5\. Managing Characters and Items

Do not put character stats in the chat log. They must be files.

**Items (`/library/items/sword_iron.json`):** A library of "definitions."

```
{"name": "Iron Sword", "damage": "1d8", "value": 10}
```

**Character (`/campaigns/.../characters/player.json`):** The character sheet references the library or stores unique data.

```
{
  "name": "Aragorn",
  "hp": 24,
  "max_hp": 30,
  "inventory": [
    "library/items/sword_iron.json",
    {"name": "Mysterious Key", "desc": "Found in the dungeon"} 
  ]
}
```

### 6\. Summary of the "Code" You Need

You effectively need **two** major instructions in your `CONVENTIONS.md` to make this work:

1.  **Startup Routine:** "At the start of every message, read `active_session.json`. ONLY modify files inside the folder listed there."
2.  **State Supremacy:** "Never trust your context window for HP or Inventory. Always read the JSON files in the active campaign folder before calculating actions."

This structure allows you to have 5 different campaigns running in parallel, with different genres and rules, without them ever leaking into each other.

## Prompt:
What should be in the agent.md and what should use the skill conversion?

## Response:
To separate the "Brain" from the "Hands," you need two distinct components.

1.  **`agent.md` (The Brain):** The prompt that tells the LLM how to behave, manage files, and narrate the story.
2.  **`dm_tools.py` (The Hands - Skill Conversion):** The Python script that handles the translation of "I want to jump" into "Strength (Athletics) Check."

Here is exactly what should be in each file.

* * *

### 1\. The `agent.md` (System Prompt)

This file is the "operating system" for your AI. It sits in the root of your workspace. When you start Aider or OpenHands, you tell it to "Read `agent.md` and follow these rules strictly."

**File Content (`agent.md`):**

```
# DUNGEON OS - SYSTEM INSTRUCTIONS

## 1. IDENTITY & GOAL
You are the **Dungeon Operating System (DungeonOS)**. You are not just a chatbot; you are a game engine that narrates a story based on rigid file states.
* **Goal:** Provide an immersive Role-Playing Game experience while maintaining strict data integrity in the JSON file system.
* **Tone:** Adaptive. (Check `config.json` in the active campaign folder for tone settings like "Dark Fantasy" or "Cyberpunk").

## 2. THE CORE LOOP (ReAct)
For every user action, you must perform this loop:
1.  **READ:** Check `active_session.json` to find the current campaign folder. Read the `state.json` and relevant `character.json` files.
2.  **THINK:** Determine what game mechanic applies (Combat, Skill Check, Save, or pure Narrative).
3.  **ACT:** Execute the appropriate script in `/system/dm_tools.py`. **DO NOT hallucinate dice rolls.**
4.  **WRITE:** Update the JSON files with the results (reduce HP, add items, change location).
5.  **NARRATE:** Describe the outcome to the player based *only* on the tool result.

## 3. FILE SYSTEM RULES
* **Source of Truth:** The file system is the ONLY source of truth. If the `hp` in `player.json` is 0, the player is dead, even if your context window thinks they are alive.
* **Persistence:** Never keep inventory or status effects in "chat memory." Always write them to the character's JSON file immediately.
* **Session Switching:** If the user asks to switch campaigns, update `active_session.json` and clear your context cache.

## 4. SKILL & COMBAT PROTOCOLS
* **Mapping:** If the user uses natural language ("I sneak", "I lie", "I bust down the door"), use the `resolve_action` tool. Do not guess the skill.
* **Combat:** Initiate combat by creating a `combat_state.json`. Track initiative and turns there.
* **Difficulty (DC):** If the user does not specify a Difficulty Class (DC), determine it based on the narrative context (Easy=10, Medium=15, Hard=20) and pass it to the tool.

## 5. FORMATTING OUTPUT
* **Narrative:** Use standard text for descriptions.
* **Meta-Data:** Use bolding for game mechanics: "**Rolled 15 (Stealth) vs DC 12 - SUCCESS**".
* **Action Required:** End with a clear prompt if the player needs to make a decision.
```

* * *

### 2\. The Skill Conversion (in `dm_tools.py`)

You do not want the AI to guess which stat corresponds to "I want to backflip." The AI might pick "Acrobatics" one time and "Athletics" the next.

You should build a **"Fuzzy Matcher"** inside your python tool. This allows the Agent to send the raw user verb, and the Code enforces the Rule System.

**File Content (`system/dm_tools.py`):**

```
import json
import random
import sys

# --- CONFIGURATION: The "Rules" Mapping ---
# This maps natural language verbs to specific D&D 5e Skills
SKILL_MAP = {
    # Strength
    "smash": "athletics", "lift": "athletics", "grapple": "athletics", "break": "athletics",
    # Dexterity
    "sneak": "stealth", "hide": "stealth", "pickpocket": "sleight_of_hand",
    "balance": "acrobatics", "flip": "acrobatics", "tumble": "acrobatics",
    # Intelligence
    "investigate": "investigation", "search": "investigation", "study": "investigation",
    "recall": "history", "remember": "history",
    # Wisdom
    "spot": "perception", "listen": "perception", "notice": "perception",
    "track": "survival", "hunt": "survival",
    "sense": "insight", "judge": "insight",
    # Charisma
    "lie": "deception", "bluff": "deception", "trick": "deception",
    "persuade": "persuasion", "convince": "persuasion", "negotiate": "persuasion",
    "intimidate": "intimidation", "threaten": "intimidation"
}

STAT_BLOCK_EXAMPLE = {
    "strength": 2, "dexterity": 3, "intelligence": 1,
    "wisdom": 0, "charisma": -1,
    "skills": {"stealth": 5, "perception": 2} # Proficiencies
}

def resolve_action(character_file, action_verb, difficulty=15):
    """
    Takes a vague user verb ('sneak') and runs the correct D&D math.
    """
    try:
        with open(character_file, 'r') as f:
            char_data = json.load(f)
    except FileNotFoundError:
        return json.dumps({"error": "Character file not found"})

    # 1. CONVERT: Map verb to skill
    # Default to a straight Ability Check if no skill matches
    skill_key = SKILL_MAP.get(action_verb.lower(), "dexterity") 
    
    # 2. CALCULATE MODIFIER
    # Check if they have specific skill proficiency, otherwise use raw stat
    if skill_key in char_data.get("skills", {}):
        modifier = char_data["skills"][skill_key]
        check_type = f"Skill Check ({skill_key.capitalize()})"
    else:
        # Fallback: Map skill to parent attribute (simplified for example)
        # In a real app, you'd map 'stealth' -> 'dexterity' lookups
        modifier = char_data.get("stats", {}).get(skill_key, 0)
        check_type = f"Ability Check ({skill_key.capitalize()})"

    # 3. ROLL
    d20 = random.randint(1, 20)
    total = d20 + modifier
    success = total >= int(difficulty)

    # 4. OUTPUT JSON FOR AGENT
    result = {
        "action_verb": action_verb,
        "check_type": check_type,
        "roll_breakdown": f"{d20} (d20) + {modifier} (mod)",
        "total": total,
        "dc": difficulty,
        "success": success,
        "narrative_cue": "You successfully perform the action." if success else "You fail, facing consequences."
    }
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    # Usage: python dm_tools.py resolve_action "chars/player.json" "sneak" 12
    cmd = sys.argv[1]
    if cmd == "resolve_action":
        resolve_action(sys.argv[2], sys.argv[3], sys.argv[4])
```

### 3\. How they talk to each other

This is the "Magic Trick." The Agent reads `agent.md` which tells it _not_ to think about rules, but to defer to the tool.

**User:** "I want to **vault** over the table."

**Agent Process:**

1.  **Consults `agent.md`:** Sees rule: _"Use `resolve_action` for physical moves."_
2.  **Constructs Command:** It sees "vault" isn't strictly defined, but it looks like a "flip" or "jump".
    *   _The Agent decides:_ "I will run `python system/dm_tools.py resolve_action 'player.json' 'flip' 12`"
    *   _(Note: The Agent maps the user's specific word to a simplified verb if needed, or passes 'vault' and lets the python script handle the fallback)._
3.  **Python Script:**
    *   Receives "flip".
    *   `SKILL_MAP` sees "flip"  $\to$  `acrobatics`.
    *   Calculates Acrobatics roll.
    *   Returns JSON: `{"success": true, "total": 18}`.
4.  **Agent Response:** "With a burst of speed, you plant your hand on the oak table and **vault** cleanly over it (Rolled 18 Acrobatics), landing ready to strike."

### Summary

*   **`agent.md`** contains the **Behavioral Logic** (Personality, File Discipline).
*   **`dm_tools.py`** contains the **Game Engine Logic** (Math, Skill Mapping).

This prevents the AI from arguing with you about rules. The code is law.

## Prompt:
I meant skills.md

The "SKILL.md" file: A "skill" is basically a folder containing a special markdown file. This file kicks off with some YAML frontmatter that gives the skill a "name" and a "description". This tells Claude what the skill does and when it should be used.

Progressive disclosure: This is where it gets pretty smart. To avoid hogging the context window, the AI doesn’t try to absorb everything at once. First, it just glances at the names and descriptions of all available skills (Level 1). If your request matches a skill, it then loads the full instructions from the "SKILL.md" file (Level 2). Finally, if those instructions point to other files, like code scripts or dense documentation, it can pull those in as needed (Level 3).

Bundled code and resources: Skills are more than just instructions; they can also pack in executable Python scripts, API docs, or other reference files. This means an agent can handle complex, predictable tasks (like filling out a PDF) perfectly every time, without needing to stuff the entire script's code into its working memory.

## Response:
This is a sophisticated architecture usually seen in "Agentic RAG" or systems like AutoGPT/BabyAGI, but applying it to D&D is brilliant. It solves the biggest problem with AI DMs: **Context Pollution.** If you load the entire _Player's Handbook_ into the context window, the AI gets confused.

By using **Progressive Disclosure**, the AI only "learns" the rules for grappling _only_ when you actually try to grapple.

Here is what that `SKILLS` architecture looks like for your DungeonOS.

### The Architecture Overview

Instead of one giant system prompt, your agent interacts with a `skills/` directory.

*   **Level 1 (The Menu):** A lightweight index telling the Agent _what_ it can do.
*   **Level 2 (The Manual):** The specific `skill.md` that teaches the Agent _how_ to handle that specific game loop.
*   **Level 3 (The Tools):** The heavy-duty Python scripts that actually _do_ the math.

* * *

### 1\. The Directory Structure

Your "Skill" is a folder containing the instructions (`skill.md`) and the tools (`scripts`).

```
/dungeon-os
├── agent.md                <-- Level 1 (The Brain)
└── /skills
    ├── /combat             <-- Skill A
    │   ├── skill.md        <-- Level 2 (The Instructions)
    │   ├── roll_hit.py     <-- Level 3 (The Code)
    │   └── calc_dmg.py
    │
    ├── /exploration        <-- Skill B
    │   ├── skill.md
    │   └── check_trap.py
    │
    └── /magic              <-- Skill C
        ├── skill.md
        └── spell_lookup.json
```

* * *

### Level 1: The "Glance" (In `agent.md`)

The Agent doesn't read the skills yet. It just knows they exist. In your root `agent.md`, you explicitly tell the agent how to navigate this structure.

**File:** `agent.md`

```
# DUNGEON OS - CORE KERNEL

## SKILL LOADER
You have access to specialized subsystems in the `/skills` directory.
DO NOT assume rules. If a user action matches a skill description below, READ that skill's `skill.md` file immediately.

## AVAILABLE SKILLS
* **Combat (`/skills/combat`):** Use when initiative is rolled, weapons are drawn, or damage is dealt.
* **Exploration (`/skills/exploration`):** Use for dungeon crawling, searching for traps, or stealth checks.
* **Magic (`/skills/magic`):** Use when a player casts a spell or uses a magic item.
* **Lore (`/skills/lore`):** Use when players ask about history, geography, or NPCs.
```

**Result:** The Agent consumes very few tokens (context) but knows exactly where to look.

* * *

### Level 2: The "Instruction" (The `skill.md`)

When the user says "I cast Fireball," the Agent realizes: _"That matches Magic."_ It then reads `/skills/magic/skill.md`.

This file contains **YAML Frontmatter** (for metadata) and **Flow Logic** (step-by-step instructions).

**File:** `/skills/magic/skill.md`

```
---
name: Magic Resolution System
description: Handles spell slots, casting logic, and save DCs.
trigger: When a player announces casting a spell.
---

# MAGIC RESOLUTION PROTOCOL

## 1. Validation
Before casting, verify the player has the resources.
* **Action:** Run `python skills/magic/check_slots.py <player_name> <spell_level>`
* **If Output is False:** Narrate the fizzle and stop.

## 2. Lookup
Retrieve the spell's specific rules.
* **Action:** Run `python skills/magic/lookup_spell.py "<spell_name>"`
* **Read Output:** Note the Range, Damage, and Saving Throw type.

## 3. Resolution
* **If Attack Roll:** Execute `python skills/combat/roll_hit.py` using the spell attack mod.
* **If Save Required:** Execute `python skills/combat/save_check.py` against the target's stats.

## 4. Cost
* **Action:** Run `python skills/magic/deduct_slot.py` to update the character sheet permanently.
```

**Result:** The Agent temporarily loads high-fidelity rules for Magic, executes them, and then can forget them once the turn is over.

* * *

### Level 3: The "Payload" (Bundled Code)

These are the hard tools that sit inside the skill folder. They are "black boxes" to the Agent—it doesn't need to read the code, just run it.

**File:** `/skills/magic/check_slots.py`

```
import sys
import json

# The agent runs this: python check_slots.py "Gandalf" 3
def check_slots(char_name, level):
    with open(f"../../campaign/chars/{char_name}.json") as f:
        data = json.load(f)
    
    slots = data['spell_slots'].get(str(level), 0)
    
    if slots > 0:
        print(json.dumps({"can_cast": True, "slots_remaining": slots}))
    else:
        print(json.dumps({"can_cast": False, "reason": "No slots left"}))

if __name__ == "__main__":
    check_slots(sys.argv[1], sys.argv[2])
```

* * *

### Example Workflow: "I check for traps."

Here is how the "Progressive Disclosure" actually flows in the chat.

1.  **User:** "I want to carefully check the door for traps."
2.  **Agent (Level 1):** Scans `agent.md`. Sees **Exploration** skill. _Internal Monologue: "This looks like an Exploration task. I will load `/skills/exploration/skill.md`."_
3.  **Agent (Level 2):** Reads `/skills/exploration/skill.md`.
    *   It sees instruction: _"For trap checks, assume the target difficulty (DC) is hidden. Use the `trap_check.py` script."_
4.  **Agent (Level 3):** Executes: `python skills/exploration/trap_check.py --player "Rogue" --location "Dungeon_Door_01"`
5.  **System Output (Hidden):**
    ```
    {
      "roll": 18,
      "detected": true,
      "trap_type": "Poison Needle",
      "mechanism": "Hidden in the handle"
    }
    ```
6.  **Agent (Narrator):** "You inspect the handle closely. A glint of metal catches your eye—a small poison needle is rigged to spring if the knob is turned."

### Why this is better for "Claude Code"

*   **Token Efficiency:** You aren't wasting 5,000 tokens describing how Grappling works when the players are just talking to a bartender.
*   **Modularity:** You can download a "Naval Combat Skill" folder from a friend, drop it in `/skills/naval`, and your Agent immediately knows how to run ship battles without you editing the core prompt.
*   **Error Isolation:** If the Magic script breaks, it doesn't crash the Combat system.

## Prompt:
Is this superior than dm\_tools? How about trait check, how would we know which trait should be check against (strength, Perception, etc)

## Response:
This is definitely superior to the monolithic `dm_tools.py` approach. It decouples the "understanding" of the action from the "calculation" of the result.

Here is why the **Skill Folder (Progressive Disclosure)** architecture wins:

1.  **Context Efficiency:** The AI isn't burdened with grappling rules while you are shopping.
2.  **Semantic Flexibility:** The AI can decide that "Intimidating the guard by crushing a rock" is a **Strength** check, not Charisma. A rigid Python script would fail to catch that nuance.
3.  **Scalability:** You can add a `/skills/crafting` folder later without breaking the combat logic.

### How to Handle Trait Checks (The "Router" Logic)

You asked: _"How would we know which trait should be checked against?"_

**The Answer:** You don't hard-code this in Python. You make the **Agent** the router (using `skill.md` instructions) and the **Script** the calculator.

Here is the exact implementation of that "Router" logic using the Skill Folder structure.

* * *

### 1\. The File Structure

We introduce a `core_mechanics` skill that handles all basic d20 rolls.

```
/skills
  └── /core_mechanics
      ├── skill.md           <-- The "Router" (Instructions)
      └── resolve_check.py   <-- The "Calculator" (Code)
```

### 2\. The Router: `skill.md` (Level 2)

This file teaches the Agent _how_ to translate user speech into game stats.

**File:** `skills/core_mechanics/skill.md`

```
---
name: Core Mechanics
description: Use this for all Ability Checks, Skill Checks, and Saving Throws.
trigger: When a player attempts an action with a chance of failure (jumping, lying, sneaking, resisting).
---

# CHECK RESOLUTION PROTOCOL

## 1. Analyze the Intent (The "Router")
You must map the user's natural language to a D&D 5e Attribute. Use your judgment:

* **Strength:** Pushing, pulling, breaking, athletics.
    * *Nuance:* Intimidating by showing physical force = Strength.
* **Dexterity:** Sneaking, balancing, sleight of hand, reflex saves.
* **Constitution:** Resisting poison, holding breath, endurance.
* **Intelligence:** Recalling lore, investigation, logical deduction.
* **Wisdom:** Perception (spotting), Insight (sensing motives), Survival.
* **Charisma:** Deception, Persuasion, Intimidation (verbal).

## 2. Determine Difficulty (DC)
If the user didn't specify a DC (Difficulty Class), set one:
* **10:** Easy (Routine task)
* **15:** Medium (Challenging)
* **20:** Hard (Expert task)

## 3. Execute the Tool
Once you have decided on the Attribute (and optional Skill), run the script.
**Do not calculate the roll yourself.**

`python skills/core_mechanics/resolve_check.py --char "PlayerName" --stat "<ATTRIBUTE>" --skill "<OPTIONAL_SKILL>" --dc <DC>`
```

### 3\. The Calculator: `resolve_check.py` (Level 3)

This script is "dumb." It doesn't know what "vaulting" is. It only knows how to add numbers.

**File:** `skills/core_mechanics/resolve_check.py`

```
import argparse
import json
import random

# In a real app, this loads from: ../../campaigns/active/characters/{name}.json
# MOCK DATA FOR DEMO
CHAR_DATA = {
    "Aragorn": {
        "stats": {"strength": 3, "dexterity": 2, "wisdom": 1},
        "proficiencies": ["athletics", "survival", "perception"]
    }
}

def resolve(char_name, stat, skill, dc):
    character = CHAR_DATA.get(char_name)
    if not character:
        return {"error": f"Character {char_name} not found"}

    # 1. Base Modifier (Stat)
    # The agent passes "strength", we look up value 3
    modifier = character["stats"].get(stat.lower(), 0)
    
    # 2. Proficiency Bonus
    # If the agent passed "athletics" and the char has it, add bonus
    prof_bonus = 2 
    is_proficient = False
    
    if skill and skill.lower() in character["proficiencies"]:
        modifier += prof_bonus
        is_proficient = True

    # 3. The Math
    d20 = random.randint(1, 20)
    total = d20 + modifier
    success = total >= dc

    # 4. JSON Output
    return {
        "narrative_data": {
            "check": f"{stat.capitalize()} ({skill.capitalize()})",
            "roll": d20,
            "mod": modifier,
            "total": total,
            "dc": dc,
            "result": "SUCCESS" if success else "FAILURE"
        }
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--char")   # e.g., "Aragorn"
    parser.add_argument("--stat")   # e.g., "strength"
    parser.add_argument("--skill")  # e.g., "athletics" (optional)
    parser.add_argument("--dc", type=int, default=15)
    args = parser.parse_args()
    
    print(json.dumps(resolve(args.char, args.stat, args.skill, args.dc)))
```

### 4\. The Workflow in Action

**User:** "I slam my fist on the table and scream at the goblin to tell me the truth!"

**The Agent (Brain):**

1.  **Reads `skill.md`**: Needs to route this.
2.  **Reasoning**: "The user is 'Intimidating'. Usually, that is Charisma. However, they are using physical force ('slam fist'). The rules say 'Intimidating by showing physical force = Strength'. I will use **Strength**."
3.  **Command**: `python skills/core_mechanics/resolve_check.py --char "Aragorn" --stat "strength" --skill "intimidation" --dc 15`

**The Script (Hand):**

1.  **Calculates**: Roll (12) + Strength Mod (3) = 15.
2.  **Output**: `{"result": "SUCCESS", "total": 15}`.

**The Agent (Narrator):**

> "You slam your fist down, cracking the wood. The goblin flinches at your raw strength (**Rolled 15 vs DC 15**). He starts stuttering, 'Okay! Okay! The base is to the North!'"

### Summary

This method is strictly better because it uses the LLM for what it is best at (**understanding context**) and the Code for what it is best at (**enforcing rules**).



---
Powered by [Gemini Exporter](https://www.ai-chat-exporter.com)