#!/usr/bin/env python3
import os
import json

class ANSESecondBrain:
    def __init__(self, memory_dir="tools/ai-second-brain/memory"):
        self.memory_dir = memory_dir
        os.makedirs(self.memory_dir, exist_ok=True)
        self.tactics_db = os.path.join(self.memory_dir, "lean_tactics.json")
        self.evasion_db = os.path.join(self.memory_dir, "red_team_evasions.json")
        
    def memorize_tactic_sequence(self, theorem_name, tactics):
        data = self._load(self.tactics_db)
        data[theorem_name] = tactics
        self._save(self.tactics_db, data)
        print(f"[Second Brain] Memorized tactic sequence for {theorem_name}.")
        
    def recall_tactic_sequence(self, theorem_name):
        data = self._load(self.tactics_db)
        return data.get(theorem_name, [])
        
    def _load(self, filepath):
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
        return {}
        
    def _save(self, filepath, data):
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)

if __name__ == "__main__":
    sb = ANSESecondBrain()
    sb.memorize_tactic_sequence("modus_tollens", ["intro hp", "apply h2", "apply h1", "exact hp"])
    print("[Second Brain] Integrated into ANSE Engine.")
