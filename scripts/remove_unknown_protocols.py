#!/usr/bin/env python3
"""
Script to remove Unknown protocols from all user profile markdown files.
"""

import re
from pathlib import Path

# List of profile files that have Unknown protocols
profile_files = [
    "0x06e8cb40376ff9f06d926e71a0740821f1914675.profile.md",
    "0x15691449477aa15e72cdff51c7b6687b58bc4e0c.profile.md",
    "0x24c8cf69a0e0a17eee21f69d29752bfa32e823e1.profile.md",
    "0x7c873c11e40ceaaba6385322d49f565b66659bd4.profile.md",
    "0x8f053ac26c46b27f304cb51ae35dc6f677e3c0b8.profile.md",
    "0x9c704d41ef1ae81a2c8ad91cfee08e404c00f9e1.profile.md",
    "0xc02147dee42356b7a4edbb1c35ac4ffa95f61fa8.profile.md",
    "0xfcf2378f20cf408d077c21e731272f21cccea469.profile.md",
]

data_dir = Path("/home/junel/random-walk-studio/polymarket/polymarket/data/user_profiles")

for filename in profile_files:
    filepath = data_dir / filename

    if not filepath.exists():
        print(f"Skipping {filename} - file not found")
        continue

    print(f"Processing {filename}...")

    # Read the file
    with open(filepath, 'r') as f:
        content = f.read()

    # Find the Unknown protocol section in detailed analysis
    # Pattern: ### N. Unknown ... --- (next section)
    unknown_section_pattern = r'###\s+\d+\.\s+Unknown\n\n.*?(?=\n---\n\n###|\n---\n\n##|\Z)'
    content = re.sub(unknown_section_pattern, '', content, flags=re.DOTALL)

    # Remove Unknown from Protocol Summary table
    unknown_row_pattern = r'\|\s+\d+\s+\|\s+\*\*Unknown\*\*\s+\|[^\n]+\n'
    content = re.sub(unknown_row_pattern, '', content)

    # Remove Unknown from Protocol Categories table
    unknown_cat_pattern = r'\|\s+Unknown\s+\|[^\n]+\n'
    content = re.sub(unknown_cat_pattern, '', content)

    # Renumber protocols in Protocol Summary
    def renumber_protocols(match):
        lines = match.group(0).split('\n')
        result_lines = []
        rank = 1
        for line in lines:
            if line.startswith('|') and '|---' not in line and 'Rank' not in line:
                # Replace rank number
                line = re.sub(r'^\|\s+\d+\s+\|', f'| {rank} |', line)
                rank += 1
            result_lines.append(line)
        return '\n'.join(result_lines)

    # Find and renumber the Protocol Summary table
    protocol_summary_pattern = r'## 📈 Protocol Summary\n\n(.*?)(?=\n## )'
    content = re.sub(protocol_summary_pattern, renumber_protocols, content, flags=re.DOTALL)

    # Renumber protocols in Detailed Protocol Analysis
    def renumber_detailed(match):
        lines = match.group(0).split('\n')
        result_lines = []
        section_num = 1
        for line in lines:
            if line.startswith('### ') and '. ' in line:
                # Replace section number
                line = re.sub(r'^###\s+\d+\.', f'### {section_num}.', line)
                section_num += 1
            result_lines.append(line)
        return '\n'.join(result_lines)

    # Find and renumber Detailed Protocol Analysis
    detailed_pattern = r'## 🔍 Detailed Protocol Analysis\n\n(.*?)(?=\n## )'
    content = re.sub(detailed_pattern, renumber_detailed, content, flags=re.DOTALL)

    # Update protocol counts
    # Count remaining protocols in summary table
    protocol_count = len(re.findall(r'\|\s+\d+\s+\|\s+\*\*[^*]+\*\*', content))

    # Update DeFi Protocols Used count in Executive Summary
    content = re.sub(
        r'(\*\*DeFi Protocols Used:\*\*\s+)\d+(\s+protocols)',
        f'\\g<1>{protocol_count}\\g<2>',
        content
    )

    # Update Protocols Identified count in Overview
    content = re.sub(
        r'(\*\*Protocols Identified:\*\*\s+)\d+',
        f'\\g<1>{protocol_count}',
        content
    )

    # Write the updated content
    with open(filepath, 'w') as f:
        f.write(content)

    print(f"  ✓ Removed Unknown protocols, updated counts to {protocol_count}")

print("\nDone! Processed all profiles.")
