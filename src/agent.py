"""
3D-Agent: Text-to-3D Blender Agent with Iterative Vision Feedback
Core module: Blender3DAgent + BlenderController
"""

import os
import json
import time
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
import yaml


class Text3DClient:
    """Client for text-to-3D API providers (Meshy, Tripo, etc.)"""
    
    def __init__(self, provider: str, api_key: str):
        self.provider = provider.lower()
        self.api_key = api_key
    
    def generate(self, prompt: str, style: str = "realistic", 
                 negative_prompt: str = "", output_format: str = "glb") -> str:
        """Generate 3D model from text prompt. Return path to downloaded file."""
        
        if self.provider == "meshy":
            return self._generate_meshy(prompt, style, negative_prompt, output_format)
        elif self.provider == "tripo":
            return self._generate_tripo(prompt, output_format)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _generate_meshy(self, prompt, style, negative_prompt, output_format):
        import requests
        
        # Step 1: Create preview task
        resp = requests.post(
            "https://api.meshy.ai/v2/text-to-3d",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "mode": "preview",
                "prompt": prompt,
                "art_style": style,
                "negative_prompt": negative_prompt
            }
        )
        resp.raise_for_status()
        task_id = resp.json()["result"]
        
        # Step 2: Poll for completion
        model_url = None
        for _ in range(60):  # Max 5 min
            status = requests.get(
                f"https://api.meshy.ai/v2/text-to-3d/{task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            ).json()
            
            if status["status"] == "SUCCEEDED":
                model_url = status["model_urls"].get(output_format, status["model_urls"]["glb"])
                break
            elif status["status"] == "FAILED":
                raise RuntimeError(f"Meshy generation failed: {status}")
            time.sleep(5)
        
        if not model_url:
            raise TimeoutError("Meshy generation timed out")
        
        # Step 3: Download
        file_path = os.path.join(tempfile.gettempdir(), f"meshy_{task_id}.{output_format}")
        r = requests.get(model_url)
        r.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(r.content)
        
        return file_path
    
    def _generate_tripo(self, prompt, output_format):
        # Tripo API via Python SDK
        try:
            import tripo3d
            client = tripo3d.Client(api_key=self.api_key)
            task = client.text_to_3d(prompt=prompt)
            task.wait()
            file_path = os.path.join(tempfile.gettempdir(), f"tripo_{task.task_id}.{output_format}")
            task.download(output=file_path)
            return file_path
        except ImportError:
            raise ImportError("Install tripo3d: pip install tripo3d")


class VisionClient:
    """Client for Vision LLM API (OpenAI GPT-4o, Anthropic Claude)"""
    
    def __init__(self, provider: str, api_key: str, model: str = "gpt-4o"):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
    
    def score_render(self, render_path: str, original_prompt: str) -> Dict:
        """Score render quality against original prompt. Return dict with score, issues, suggestions."""
        
        if self.provider == "openai":
            return self._score_openai(render_path, original_prompt)
        elif self.provider == "anthropic":
            return self._score_anthropic(render_path, original_prompt)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _score_openai(self, render_path, original_prompt):
        from openai import OpenAI
        import base64
        
        client = OpenAI(api_key=self.api_key)
        
        with open(render_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert 3D art director. Score how well a rendered image "
                        "matches a text prompt. Return ONLY a JSON object with this exact schema: "
                        '{"score": 0-100, "issues": ["issue1", "issue2"], "suggestions": ["action1", "action2"]}'
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Original prompt: {original_prompt}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.2
        )
        
        content = response.choices[0].message.content
        # Extract JSON from possible markdown code block
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        return json.loads(content)
    
    def _score_anthropic(self, render_path, original_prompt):
        import anthropic
        import base64
        
        client = anthropic.Anthropic(api_key=self.api_key)
        
        with open(render_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        response = client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Score 0-100 how well this render matches the prompt: '{original_prompt}'. "
                            "Return ONLY JSON: {\"score\": number, \"issues\": [\"...\"], \"suggestions\": [\"...\"]}"
                        )
                    }
                ]
            }]
        )
        
        content = response.content[0].text
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        return json.loads(content)


class BlenderController:
    """Wrapper around Blender Python API (bpy) for headless scene manipulation."""
    
    def __init__(self, blender_path: str = "/usr/bin/blender"):
        self.blender_path = blender_path
        self.scene_script = ""
    
    def _run_blender_script(self, script: str, output_dir: str = "/tmp") -> str:
        """Execute Blender in background mode with given Python script."""
        script_path = os.path.join(output_dir, "blender_temp_script.py")
        with open(script_path, "w") as f:
            f.write(script)
        
        cmd = [
            self.blender_path,
            "--background",
            "--python", script_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"Blender error: {result.stderr}")
        
        return result.stdout
    
    def generate_scene_script(self, model_path: str, render_output: str,
                            camera_pos=(5, -5, 3), light_energy=1000,
                            resolution=1024, engine="CYCLES", samples=128) -> str:
        """Generate a Blender Python script for scene setup and render."""
        
        ext = os.path.splitext(model_path)[1].lower()
        if ext == ".glb":
            import_cmd = f'bpy.ops.import_scene.gltf(filepath=r"{model_path}")'
        elif ext == ".obj":
            import_cmd = f'bpy.ops.import_scene.obj(filepath=r"{model_path}")'
        elif ext == ".fbx":
            import_cmd = f'bpy.ops.import_scene.fbx(filepath=r"{model_path}")'
        else:
            raise ValueError(f"Unsupported format: {ext}")
        
        script = f'''
import bpy
import math

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Remove default objects
for obj in bpy.data.objects:
    if obj.type in ('MESH', 'LIGHT', 'CAMERA'):
        bpy.data.objects.remove(obj, do_unlink=True)

# Import model
{import_cmd}

# Center and scale imported objects
imported_objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
if imported_objects:
    # Join all meshes for easier manipulation
    bpy.context.view_layer.objects.active = imported_objects[0]
    for obj in imported_objects[1:]:
        obj.select_set(True)
    if len(imported_objects) > 1:
        bpy.ops.object.join()
    
    main_obj = bpy.context.active_object
    # Reset origin to geometry center
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    main_obj.location = (0, 0, 0)
    
    # Auto-scale to fit in view
    dims = main_obj.dimensions
    max_dim = max(dims)
    if max_dim > 0:
        scale = 2.0 / max_dim
        main_obj.scale = (scale, scale, scale)

# Camera
cam_data = bpy.data.cameras.new("Camera")
cam_obj = bpy.data.objects.new("Camera", cam_data)
bpy.context.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj
cam_obj.location = {camera_pos}
cam_obj.rotation_euler = (math.radians(60), 0, math.radians(45))

# Lights
light_data = bpy.data.lights.new("KeyLight", type='SUN')
light_obj = bpy.data.objects.new("KeyLight", light_data)
bpy.context.collection.objects.link(light_obj)
light_obj.location = (3, 3, 5)
light_obj.rotation_euler = (math.radians(45), 0, math.radians(45))
light_data.energy = {light_energy}

# Fill light
fill_data = bpy.data.lights.new("FillLight", type='AREA')
fill_obj = bpy.data.objects.new("FillLight", fill_data)
bpy.context.collection.objects.link(fill_obj)
fill_obj.location = (-3, -2, 3)
fill_data.energy = {light_energy * 0.3}

# World background
world = bpy.context.scene.world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Strength"].default_value = 0.5
bg.inputs["Color"].default_value = (0.05, 0.05, 0.1, 1)

# Render settings
scene = bpy.context.scene
scene.render.engine = '{engine}'
scene.render.resolution_x = {resolution}
scene.render.resolution_y = {resolution}
scene.render.resolution_percentage = 100
scene.render.filepath = r"{render_output}"

if '{engine}' == 'CYCLES':
    scene.cycles.samples = {samples}
    scene.cycles.device = 'CPU'

# Render
bpy.ops.render.render(write_file=True)
print(f"RENDER_COMPLETE: {render_output}")
'''
        return script
    
    def render_model(self, model_path: str, output_path: str, **kwargs) -> str:
        """Import model and render to image."""
        script = self.generate_scene_script(model_path, output_path, **kwargs)
        self._run_blender_script(script)
        return output_path
    
    def apply_modifications(self, model_path: str, suggestions: List[str], 
                          output_path: str, **kwargs) -> str:
        """Apply Vision LLM suggestions to scene and re-render."""
        
        modification_script = self._parse_suggestions_to_script(suggestions)
        
        base_script = self.generate_scene_script(model_path, output_path, **kwargs)
        
        # Insert modifications before render
        script = base_script.replace(
            "# Render",
            f"# Modifications from Vision LLM\n{modification_script}\n\n# Render"
        )
        
        self._run_blender_script(script)
        return output_path
    
    def _parse_suggestions_to_script(self, suggestions: List[str]) -> str:
        """Convert natural language suggestions to bpy commands."""
        commands = []
        
        for suggestion in suggestions:
            s = suggestion.lower()
            
            if any(word in s for word in ["red", "blue", "green", "yellow", "purple", "orange"]):
                # Color change
                color_map = {
                    "red": "(1.0, 0.0, 0.0, 1.0)",
                    "blue": "(0.0, 0.0, 1.0, 1.0)",
                    "green": "(0.0, 1.0, 0.0, 1.0)",
                    "yellow": "(1.0, 1.0, 0.0, 1.0)",
                    "purple": "(0.5, 0.0, 0.5, 1.0)",
                    "orange": "(1.0, 0.5, 0.0, 1.0)"
                }
                for color_name, color_val in color_map.items():
                    if color_name in s:
                        commands.append(f'''
for mat in bpy.data.materials:
    if mat.use_nodes:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = {color_val}
''')
                        break
            
            if "emission" in s or "glow" in s or "light" in s:
                # Boost emission
                strength = 5.0 if "strong" in s or "more" in s else 2.0
                commands.append(f'''
for mat in bpy.data.materials:
    if mat.use_nodes:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Emission Strength"].default_value = {strength}
''')
            
            if "move camera" in s or "closer" in s or "farther" in s:
                # Adjust camera
                commands.append('''
cam = bpy.data.objects.get("Camera")
if cam:
    cam.location = (cam.location[0] * 0.7, cam.location[1] * 0.7, cam.location[2])
''')
            
            if "brighter" in s or "darker" in s:
                factor = 1.5 if "brighter" in s else 0.6
                commands.append(f'''
for light in bpy.data.lights:
    light.energy *= {factor}
''')
        
        return "\n".join(commands) if commands else "# No applicable modifications"


class Blender3DAgent:
    """
    Main agent orchestrating the text-to-3D pipeline with iterative optimization.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        
        self.text3d = Text3DClient(
            self.config["TEXT3D_PROVIDER"],
            self.config["TEXT3D_API_KEY"]
        )
        self.vision = VisionClient(
            self.config["VISION_PROVIDER"],
            self.config["VISION_API_KEY"],
            self.config.get("VISION_MODEL", "gpt-4o")
        )
        self.blender = BlenderController(self.config.get("BLENDER_PATH", "/usr/bin/blender"))
        
        self.max_iterations = self.config.get("MAX_ITERATIONS", 5)
        self.score_threshold = self.config.get("SCORE_THRESHOLD", 85)
        self.output_dir = Path(self.config.get("OUTPUT_DIR", "./output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(self, prompt: str, style: str = "realistic") -> Dict:
        """
        Main pipeline: prompt → 3D model → render → iterate → result.
        Returns dict with final render path, score, and iteration history.
        """
        
        history = []
        start_time = time.time()
        
        # Step 1: Generate 3D model
        print(f"[1/5] Generating 3D model for: '{prompt}'")
        model_path = self.text3d.generate(prompt, style=style)
        history.append({"step": "generate", "model_path": model_path})
        
        # Step 2: Initial render
        print(f"[2/5] Rendering initial scene...")
        render_v0 = str(self.output_dir / "render_v0.png")
        self.blender.render_model(
            model_path, render_v0,
            resolution=self.config.get("RENDER_RESOLUTION", 1024),
            engine=self.config.get("RENDER_ENGINE", "CYCLES"),
            samples=self.config.get("RENDER_SAMPLES", 128)
        )
        history.append({"step": "render", "iteration": 0, "path": render_v0})
        
        # Step 3-5: Iterative optimization
        best_render = render_v0
        best_score = 0
        
        for i in range(self.max_iterations):
            print(f"[3/5] Vision evaluation (iteration {i+1}/{self.max_iterations})...")
            feedback = self.vision.score_render(best_render, prompt)
            score = feedback.get("score", 0)
            
            print(f"  → Score: {score}/100")
            print(f"  → Issues: {feedback.get('issues', [])}")
            print(f"  → Suggestions: {feedback.get('suggestions', [])}")
            
            history.append({
                "step": "evaluate",
                "iteration": i + 1,
                "score": score,
                "feedback": feedback
            })
            
            if score > best_score:
                best_score = score
                
            if score >= self.score_threshold:
                print(f"✅ Threshold reached! Stopping at iteration {i+1}")
                break
            
            if not feedback.get("suggestions"):
                print("⚠️ No suggestions provided. Stopping.")
                break
            
            # Apply modifications and re-render
            print(f"[4/5] Applying modifications...")
            next_render = str(self.output_dir / f"render_v{i+1}.png")
            self.blender.apply_modifications(
                model_path, feedback["suggestions"], next_render,
                resolution=self.config.get("RENDER_RESOLUTION", 1024),
                engine=self.config.get("RENDER_ENGINE", "CYCLES"),
                samples=self.config.get("RENDER_SAMPLES", 128)
            )
            best_render = next_render
            history.append({"step": "render", "iteration": i+1, "path": next_render})
        
        total_time = time.time() - start_time
        
        result = {
            "prompt": prompt,
            "final_render": best_render,
            "best_score": best_score,
            "iterations": len([h for h in history if h["step"] == "evaluate"]),
            "total_time_sec": round(total_time, 2),
            "history": history
        }
        
        # Save result metadata
        result_path = self.output_dir / "result.json"
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Done! Final score: {best_score}/100")
        print(f"   Render: {best_render}")
        print(f"   Metadata: {result_path}")
        
        return result


if __name__ == "__main__":
    # Demo usage
    agent = Blender3DAgent("config.yaml")
    result = agent.generate("a red sports car in a dark garage with neon lights")
    print(json.dumps(result, indent=2, ensure_ascii=False))
