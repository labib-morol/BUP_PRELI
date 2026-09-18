import json
import asyncio
import os
from google import genai
from google.genai import types

# Load prompt module
import sys
sys.path.insert(0, 'c:/Users/T14S/BUP Hackathon')
import app.prompt as prompt

async def run_single():
    with open("tools/notes_corpus.json") as f:
        corpus = json.load(f)["entries"]
    
    # We will use .env key
    with open(".env") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                os.environ["GEMINI_API_KEY"] = line.strip().split("=")[1]
    
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    system = f"{prompt.SYSTEM_PROMPT}\n\nEXAMPLES\n{prompt.build_few_shot_block()}"
    
    correct = 0
    
    for entry in corpus:
        capacity_kwh = entry["capacity_kwh"]
        initial_kwh, minimum_kwh = capacity_kwh * 0.5, capacity_kwh * 0.2
        user = prompt.build_user_prompt([entry["note"]], capacity_kwh, initial_kwh, minimum_kwh)
        
        for attempt in range(5):
            try:
                resp = await client.aio.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=user,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        temperature=0,
                        response_mime_type="application/json",
                    )
                )
                break
            except Exception as e:
                if attempt == 4:
                    raise
                await asyncio.sleep(2)
        
        try:
            data = json.loads(resp.text)
            directive = data["directives"][0]
            # compare with expect
            expect = entry["expect"]
            
            # Simple check
            match = True
            if directive.get("directive_type") != expect.get("directive_type", "no_op"): match = False
            
            if expect.get("applies", False):
                if tuple(directive.get("hours", [])) != tuple(expect.get("hours", [])): match = False
                for k in ["factor", "minimum_energy_kwh", "max_grid_kwh"]:
                    if k in expect:
                        if directive.get(k) is None or abs(directive.get(k) - expect[k]) > 0.51:
                            match = False
            if match:
                correct += 1
            else:
                print(f"Failed {entry['id']}: expected {expect}, got {directive}")
        except Exception as e:
            print(f"Error on {entry['id']}: {e}")
            
    print(f"Accuracy: {correct}/{len(corpus)}")

if __name__ == '__main__':
    asyncio.run(run_single())
