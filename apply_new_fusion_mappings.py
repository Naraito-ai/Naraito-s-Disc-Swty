# -*- coding: utf-8 -*-
"""
apply_new_fusion_mappings.py - Replaces NBA_FUSION_GIF_MAPPINGS in nba_data.py with authoritative verified mappings.
"""
import re

from generate_final_fusion_mappings import FINAL_MAPPINGS

# Update Allen Iverson alias to distinct verified GIF
FINAL_MAPPINGS["go-iverson-97"]["gif_url"] = "https://media.tenor.com/1EWb9d-a80cAAAAM/iverson-crossover.gif"
FINAL_MAPPINGS["go-alleniverson-97"]["gif_url"] = "https://media.tenor.com/EEdRX92hjD4AAAAM/allen-iverson-michael-jordan.gif"

# Format new dictionary code
dict_lines = ["NBA_FUSION_GIF_MAPPINGS = {"]
for cid, info in sorted(FINAL_MAPPINGS.items()):
    dict_lines.append(f"  '{cid}': {{")
    dict_lines.append(f"    'name': {repr(info['name'])},")
    dict_lines.append(f"    'gif_url': {repr(info['gif_url'])},")
    dict_lines.append(f"    'flavor_text': {repr(info['flavor_text'])}")
    dict_lines.append("  },")
dict_lines[-1] = dict_lines[-1].rstrip(",") + "\n}"
formatted_code = "\n".join(dict_lines)

with open("nba_data.py", "r", encoding="utf-8") as f:
    content = f.read()

pattern = r"NBA_FUSION_GIF_MAPPINGS = \{.*?'Willis Reed'\}\}"
match = re.search(pattern, content, re.DOTALL)
if match:
    new_content = content[:match.start()] + formatted_code + content[match.end():]
    with open("nba_data.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully updated NBA_FUSION_GIF_MAPPINGS in nba_data.py!")
else:
    print("Could not find NBA_FUSION_GIF_MAPPINGS block in nba_data.py")
