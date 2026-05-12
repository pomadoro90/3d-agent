# 🎨 3D-Agent: Text-to-3D Blender Agent Starter Kit

> **Концепт:** AI-агент, который генерирует 3D-сцены в Blender по текстовому описанию, рендерит их, сравнивает результат с промптом через Vision LLM, и итеративно доводит сцену до идеального состояния.
>
> **Архитектура:** API-only (без локальных LLM/диффузионных моделей) → подходит для серверов с ограниченными ресурсами.

---

## 📐 Архитектура системы

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Пользователь  │────→│  Text-to-3D API  │────→│   3D Модель     │
│  (text prompt)  │     │ (Meshy/Tripo/etc)│     │   (.glb/.obj)   │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                        │
                         ┌──────────────────┐            │
                         │   Vision LLM API │←───────────┘
                         │  (GPT-4o/Claude) │    (render image)
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │  Feedback Loop   │
                         │  (score + diff)  │
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │  Blender (bpy)     │
                         │  Scene → Render   │
                         └───────────────────┘
```

### Поток данных
1. **Пользователь** вводит текстовый промпт (`"cyberpunk robot with neon lights"`)
2. **Text-to-3D API** генерирует 3D-модель (`mesh + texture`)
3. **Blender** импортирует модель, создаёт сцену (камера, свет, фон), рендерит
4. **Vision LLM API** анализирует рендер и сравнивает с оригинальным промптом
5. **Feedback Loop** выдаёт `score` + список корректировок (`"add more red lights"`)
6. **Blender** модифицирует сцену (материалы, освещение, позиция камеры)
7. **Повтор** шагов 4–6 до достижения `score >= threshold` или `max_iterations`

---

## 🔌 Компоненты (API-only)

### 1. Text-to-3D API (выбор провайдера)

| Провайдер | Цена | Free Tier | Форматы | Скорость | Примечания |
|-----------|------|-----------|---------|----------|------------|
| **Meshy** | $5/мес (Pro) | 200 cr/мес | `.glb`, `.obj`, `.blend`, `.fbx` | 1–3 мин | Есть Blender-плагин, отличная документация |
| **Tripo AI** | от $19/мес | 10 tasks/мес | `.glb`, `.obj` | 10–60 сек | Есть Blender-плагин + Python SDK (`pip install tripo3d`) |
| **3D AI Studio** | Pay-per-request | Нет | `.glb` + PBR | 20 сек–4 мин | Агрегатор (Hunyuan3D, TRELLIS) — один API, множество моделей |
| **Hunyuan3D (Tencent)** | Через 3DAI | — | `.glb` | <60 сек | 8K PBR текстуры, до 2M полигонов |
| **Scenario** | от $9/мес | 100 cr | `.glb`, `.obj` | 30–120 сек | Специализация на game-ready assets |

**Рекомендация для старта:** Meshy (Pro $5) — самый дешёвый старт + нативный Blender-плагин + поддержка `.blend`.

#### Пример: генерация через Meshy API
```python
import requests

API_KEY = "your_meshy_api_key"

# Step 1: Создать preview (геометрия без текстуры)
resp = requests.post(
    "https://api.meshy.ai/v2/text-to-3d",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={
        "mode": "preview",
        "prompt": "A cyberpunk robot with neon blue lights",
        "art_style": "realistic",
        "negative_prompt": "low poly, blurry"
    }
)
task_id = resp.json()["result"]

# Step 2: Poll until done
import time
while True:
    status = requests.get(
        f"https://api.meshy.ai/v2/text-to-3d/{task_id}",
        headers={"Authorization": f"Bearer {API_KEY}"}
    ).json()
    if status["status"] == "SUCCEEDED":
        model_url = status["model_urls"]["glb"]
        break
    time.sleep(5)
```

---

### 2. Blender Python API (`bpy`)

Blender полностью управляется через Python-скрипты (`bpy`). Ключевые операции:

#### Импорт модели
```python
import bpy

# Очистить сцену
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Импорт .glb
bpy.ops.import_scene.gltf(filepath="/path/to/model.glb")

# Импорт .obj
# bpy.ops.import_scene.obj(filepath="/path/to/model.obj")
```

#### Создание сцены: камера, свет, фон
```python
import bpy
import math

# Камера
cam_data = bpy.data.cameras.new("Camera")
cam_obj = bpy.data.objects.new("Camera", cam_data)
bpy.context.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

# Позиция камеры (изометрия)
cam_obj.location = (5, -5, 3)
cam_obj.rotation_euler = (math.radians(60), 0, math.radians(45))

# Точечный свет
light_data = bpy.data.lights.new("Light", type='POINT')
light_obj = bpy.data.objects.new("Light", light_data)
bpy.context.collection.objects.link(light_obj)
light_obj.location = (3, 3, 5)
light_data.energy = 1000

# HDRI / Environment (для реалистичного освещения)
world = bpy.context.scene.world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Strength"].default_value = 1.0
# bg.inputs["Color"].default_value = (0.05, 0.05, 0.1, 1)  # тёмно-синий фон
```

#### Рендер
```python
# Настройки рендера
scene = bpy.context.scene
scene.render.engine = 'CYCLES'  # или 'BLENDER_EEVEE' для скорости
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024
scene.render.filepath = "/tmp/render_output.png"

# Рендер
bpy.ops.render.render(write_file=True)
```

#### Модификация материалов (для feedback loop)
```python
# Найти материал по имени
mat = bpy.data.materials.get("Material.001")
if mat and mat.use_nodes:
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        # Изменить цвет
        bsdf.inputs["Base Color"].default_value = (1.0, 0.0, 0.0, 1.0)  # красный
        # Увеличить emission (свечение)
        bsdf.inputs["Emission Strength"].default_value = 5.0
        bsdf.inputs["Emission"].default_value = (0.0, 0.8, 1.0, 1.0)  # голубое свечение
```

#### Изменение позиции объекта
```python
obj = bpy.data.objects.get("Imported_Model")
if obj:
    obj.location = (0, 0, 0)
    obj.rotation_euler = (0, 0, math.radians(15))
    obj.scale = (1.2, 1.2, 1.2)
```

---

### 3. Vision LLM API (оценка качества рендера)

Vision LLM анализирует рендер и сравнивает с оригинальным промптом.

#### OpenAI GPT-4o Vision
```python
from openai import OpenAI
import base64

client = OpenAI(api_key="your_openai_key")

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def score_render(render_path, original_prompt):
    base64_image = encode_image(render_path)
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are an expert 3D art director. Score how well a rendered image matches a text prompt. Return ONLY a JSON: {\"score\": 0-100, \"issues\": [\"issue1\", \"issue2\"], \"suggestions\": [\"action1\", \"action2\"]}"
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Original prompt: {original_prompt}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                ]
            }
        ],
        max_tokens=500
    )
    
    return response.choices[0].message.content

# Пример
result = score_render("/tmp/render_output.png", "cyberpunk robot with neon blue lights")
# Возвращает: {"score": 72, "issues": ["not enough neon lights", "robot looks too generic"], "suggestions": ["increase emission strength on robot chest", "add point lights with blue color"]}
```

#### Альтернатива: Anthropic Claude 3 Sonnet
```python
import anthropic

client = anthropic.Anthropic(api_key="your_anthropic_key")

def score_render_claude(render_path, original_prompt):
    with open(render_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    
    response = client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_data}},
                {"type": "text", "text": f"Score 0-100 how well this render matches: '{original_prompt}'. Return JSON with score, issues, suggestions."}
            ]
        }]
    )
    return response.content[0].text
```

---

## 🔄 Feedback Loop (ядро агента)

```python
class Blender3DAgent:
    def __init__(self, text3d_api, vision_api, max_iterations=5, score_threshold=85):
        self.text3d_api = text3d_api      # Meshy/Tripo client
        self.vision_api = vision_api        # GPT-4o/Claude client
        self.max_iterations = max_iterations
        self.score_threshold = score_threshold
    
    def generate(self, prompt: str) -> str:
        """Основной пайплайн: prompt → 3D → render → iterate → result"""
        
        # 1. Генерация 3D-модели
        model_path = self.text3d_api.generate(prompt)
        
        # 2. Импорт в Blender и первый рендер
        blender = BlenderController()
        blender.clear_scene()
        blender.import_model(model_path)
        blender.setup_scene()
        render_path = blender.render("/tmp/render_v0.png")
        
        # 3. Итеративная оптимизация
        for i in range(self.max_iterations):
            # Оценка
            feedback = self.vision_api.score(render_path, prompt)
            score = feedback["score"]
            
            print(f"Iteration {i}: score={score}")
            
            if score >= self.score_threshold:
                break
            
            # Применить корректировки
            blender.apply_suggestions(feedback["suggestions"])
            render_path = blender.render(f"/tmp/render_v{i+1}.png")
        
        return render_path

class BlenderController:
    def __init__(self):
        import bpy
        self.bpy = bpy
    
    def clear_scene(self):
        self.bpy.ops.object.select_all(action='SELECT')
        self.bpy.ops.object.delete(use_global=False)
    
    def import_model(self, path: str):
        if path.endswith(".glb"):
            self.bpy.ops.import_scene.gltf(filepath=path)
        elif path.endswith(".obj"):
            self.bpy.ops.import_scene.obj(filepath=path)
    
    def setup_scene(self):
        # Камера, свет, фон (см. примеры выше)
        pass
    
    def apply_suggestions(self, suggestions: list):
        """Парсинг suggestions и применение в Blender"""
        for suggestion in suggestions:
            if "increase emission" in suggestion.lower():
                self._boost_emission()
            elif "add point light" in suggestion.lower():
                color = self._extract_color(suggestion)
                self._add_point_light(color)
            elif "move camera" in suggestion.lower():
                self._adjust_camera(suggestion)
            # ... и т.д.
    
    def render(self, output_path: str) -> str:
        self.bpy.context.scene.render.filepath = output_path
        self.bpy.ops.render.render(write_file=True)
        return output_path
```

---

## 📊 Метрики и логирование

| Метрика | Как считать | Цель |
|---------|-------------|------|
| **Prompt adherence score** | Vision LLM (0–100) | ≥ 85 |
| **Render time** | `time.time()` diff | < 30 сек (EEVEE) |
| **3D generation time** | API response time | < 3 мин |
| **Iterations to converge** | Счётчик цикла | ≤ 5 |
| **Cost per scene** | API costs sum | < $0.50 |

---

## 🛠 Технический стек

```
Python 3.10+
├── Blender 4.x (bpy модуль)
├── text-to-3d API client (Meshy/Tripo/3DAI)
├── vision-llm client (openai / anthropic)
├── PIL / Pillow (обработка рендеров)
├── json (feedback parsing)
└── logging (отслеживание итераций)
```

---

## 🚀 Быстрый старт (MVP за 1 день)

### Шаг 1: Blender + bpy
```bash
# Установить Blender
sudo apt install blender

# Проверить Python API
blender --background --python -c "import bpy; print(bpy.app.version)"
```

### Шаг 2: API-ключи
- [Meshy Dashboard](https://www.meshy.ai/) → API Key
- [OpenAI Platform](https://platform.openai.com/) → API Key
- [Tripo AI](https://www.tripo3d.ai/) → API Key (опционально)

### Шаг 3: Первая сцена
```bash
git clone https://github.com/pomadoro90/3d-agent.git
cd 3d-agent
pip install -r requirements.txt
python examples/first_scene.py --prompt "a red sports car in a garage"
```

---

## 📁 Структура репозитория

```
3d-agent/
├── README.md                    # Этот файл
├── requirements.txt             # Зависимости
├── config.yaml                  # API keys, настройки
├── src/
│   ├── __init__.py
│   ├── agent.py                 # Главный класс Blender3DAgent
│   ├── text3d_api.py           # Клиенты Meshy/Tripo/3DAI
│   ├── vision_api.py           # GPT-4o / Claude
│   ├── blender_controller.py   # Обёртка над bpy
│   └── feedback_parser.py      # Парсинг suggestions → bpy команды
├── examples/
│   ├── first_scene.py          # MVP: prompt → render
│   ├── iterative_optimization.py  # Полный feedback loop
│   └── batch_generation.py    # Массовая генерация
├── tests/
│   └── test_blender_controller.py
└── docs/
    ├── meshy_api_reference.md
    ├── blender_bpy_cheatsheet.md
    └── vision_prompt_engineering.md
```

---

## 🔗 Ресурсы и документация

### Text-to-3D API
- [Meshy API Docs](https://docs.meshy.ai/api/text-to-3d)
- [Tripo Python SDK (PyPI)](https://pypi.org/project/tripo3d/)
- [3D AI Studio API](https://www.3daistudio.com/Platform/API/Documentation)
- [Hunyuan3D GitHub](https://github.com/Tencent/HunyuanDiT)

### Blender Python
- [Blender Python API Reference](https://docs.blender.org/api/current/)
- [bpy.ops.import_scene](https://docs.blender.org/api/current/bpy.ops.import_scene.html)
- [StackExchange: Script import and render](https://blender.stackexchange.com/questions/39303)

### Vision LLM
- [OpenAI Vision Guide](https://getstream.io/blog/gpt-4o-vision-guide/)
- [Anthropic Vision Docs](https://docs.anthropic.com/en/docs/build-with-claude/vision)
- [Prompt engineering for image analysis](https://platform.openai.com/docs/guides/vision)

### Open-source аналоги (для вдохновения)
- [ThreeStudio](https://github.com/threestudio-project/threestudio) — unified text-to-3D framework (требует GPU)
- [Infinigen](https://github.com/princeton-vl/infinigen) — procedural 3D scene generation
- [Tripo Blender Plugin](https://github.com/VAST-AI-Research/tripo-3d-for-blender)
- [Meshy Blender Plugin](https://www.meshy.ai/blog/blender-ai-plugin)

---

## 💡 Идеи для развития

| Фича | Сложность | Описание |
|------|-----------|----------|
| **Multi-view render** | Лёгкая | 4 ракурса → оценка каждого Vision LLM |
| **Animation generation** | Средняя | Генерация 360° вращения объекта |
| **Scene composition** | Средняя | Несколько объектов + фон + эффекты |
| **PBR material tuning** | Средняя | Vision LLM → корректировка roughness/metallic |
| **Style transfer** | Сложная | Применение стиля к существующей 3D-модели |
| **Physics simulation** | Сложная | Добавление rigid body / cloth / fluid |

---

## ⚠️ Ограничения и риски

1. **Стоимость API** — каждая итерация = 1 text-to-3D call + 1 vision call. С лимитом 5 итераций: ~$0.30–0.50/сцена.
2. **Latency** — text-to-3D API 1–3 мин. Для интерактивного использования кешируйте модели.
3. **Vision LLM не идеален** — может "галлюцинировать" оценки. Добавьте human-in-the-loop для критичных задач.
4. **Blender headless** — на сервере без GPU рендер EEVEE работает на CPU (медленно). Используйте CYCLES с low samples.

---

## 📜 Лицензия

MIT License — свободно для коммерческого и некоммерческого использования.

---

*Generated by slider-1 for pomadoro90 | 2026-05-12*
