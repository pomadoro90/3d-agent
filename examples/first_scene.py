#!/usr/bin/env python3
"""
3D-Agent: First Scene Example
MVP: text prompt → 3D model → render
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent import Blender3DAgent

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate 3D scene from text prompt")
    parser.add_argument("--prompt", type=str, default="a red sports car in a dark garage",
                        help="Text description of the scene")
    parser.add_argument("--style", type=str, default="realistic",
                        help="Art style (realistic, stylized, etc.)")
    parser.add_argument("--config", type=str, default="config.yaml",
                        help="Path to config file")
    args = parser.parse_args()
    
    print("🎨 3D-Agent: First Scene")
    print(f"Prompt: {args.prompt}")
    print("-" * 50)
    
    agent = Blender3DAgent(args.config)
    result = agent.generate(args.prompt, style=args.style)
    
    print("\n📊 Result:")
    print(f"  Final render: {result['final_render']}")
    print(f"  Best score: {result['best_score']}/100")
    print(f"  Iterations: {result['iterations']}")
    print(f"  Total time: {result['total_time_sec']}s")
