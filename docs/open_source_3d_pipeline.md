# 🧠 Open-source pipeline: LLM → Python Script → Blender (без diffusion-моделей)

> **Концепт:** Не вызывать внешние text-to-3D API (Meshy/Tripo), а научить обычный LLM писать Python-скрипты для Blender. Blender исполняет код → рендерит модель → результат.
> 
> **Преимущество:** Не нужен GPU. Нужен только Blender + LLM (через API или маленькую локальную модель).

---

## 🏆 Топ решений на GitHub

| Проект | ⭐ | Подход | LLM | Статус |
|--------|-----|--------|-----|--------|
| **LL3M** | 531 | Multi-agent writes Python scripts | Claude Sonnet 3.7 ( retired! ⚠️ ) | **Server discontinued** |
| **BlenderLLM** | 246 | Тонко настроенный Qwen пишет CAD-скрипты | **Qwen2.5-Coder-7B-Instruct** (fine-tuned) | ✅ Активен |
| **BlenderLM** | 14 | REST API wrapper для LLM агентов | GPT-4.1-mini, любой через API | ✅ Активен |
| **TreeGen-LLM** | ? | Генерирует деревья через Geometry Nodes + мелкий LLM | Лёгкий LLM | ✅ Активен |

**Рекомендация:** BlenderLLM — он не требует Claude, не требует тяжёлого сервера, не устарел. Это small model (7B), которая уже обучена на 12k Blender-скриптов и бьёт Claude/GPT по качеству генерации CAD-кода.

---

## 🥇 BlenderLLM — детали

**Репозиторий:** https://github.com/FreedomIntelligence/BlenderLLM

**Что это:**
- Неплохо настроенная **Qwen2.5-Coder-7B-Instruct** → output: Python `bpy`-скрипт
- Обучена на **12k** парах `<инструкция, скрипт>` из Blender
- Датасет: **BlendNet** (2k руками + 10k GPT-4o)

**Оценка (CADBench):**

| Модель | CADBench Sim Avg ↑ | Syntax Error ↓ |
|--------|-------------------|----------------|
| **BlenderLLM** | **0.748** | **3.4%** |
| o1-Preview | 0.687 | 15.6% |
| GPT-4-Turbo | 0.589 | 18.2% |
| Claude-3.5-Sonnet | 0.593 | 15.6% |
| GPT-4o | 0.565 | 21.4% |

**Вывод:** BlenderLLM даёт **лучшие скрипты** чем коммерческие LLM, и при этом это **7B модель** — можно запустить локально!

---

### 🚀 Быстрый старт BlenderLLM

```bash
# 1. Скачать и установить Blender (для рендера)
blender --version  # проверить

# 2. Скачать модель с HuggingFace
pip install transformers torch
# python -c "from transformers import AutoModelForCausalLM; ..."  # скачать BlenderLLM

# 3. Сгенерировать скрипт
python chat.py \
    --model_name "FreedomIntelligence/BlenderLLM" \
    --prompt "create a low-poly tree with green leaves and brown trunk"

# 4. Исполнить скрипт в Blender и отрендерить
python modeling.py \
    --model_name "FreedomIntelligence/BlenderLLM" \
    --prompt "create a low-poly tree with green leaves and brown trunk" \
    --obj_name "lowpoly_tree" \
    --output_folder "./output" \
    --blender_executable "/usr/bin/blender" \
    --brightness 1.2
```

---

## 🔄 Как интегрировать в твой 3D-Agent

### Архитектура (новая версия)

```
┌──────────────┐     ┌──────────────────────────┐     ┌──────────────┐
│ Пользователь │────→│  LLM (Qwen2.5-Coder-7B   │────→│    Blender   │
│  (prompt)    │     │  или BlenderLLM)         │     │  (headless)  │
└──────────────┘     └──────────────────────────┘     └──────┬───────┘
                                                            │
                         ┌──────────────┐                   │
                         │ Vision LLM   │←──────────────────┘
                         │  GPT-4o      │    (render image)
                         └──────────────┘
```

### Pipeline

1. **Пользователь** → `"create a detailed chess rook piece"`
2. **LLM** → генерирует Python-скрипт (пример ниже):
3. **Blender** → исполняет скрипт headless (`blender -b --python script.py`)
4. **Blender** → рендерит в PNG (`render_output.png`)
5. **Vision LLM** → оценивает рендер, сравнивает с промптом
6. **Если score < threshold** → LLM получает feedback, дорабатывает скрипт
7. **Повтор** шагов 3-6

---

### Пример сгенерированного скрипта BlenderLLM

```python
import bpy
import bmesh
import math

# Очистить сцену
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Создать цилиндр (тело фигуры)
bpy.ops.mesh.primitive_cylinder_add(
    vertices=32,
    radius=0.5,
    depth=2.0,
    location=(0, 0, 1)
)
body = bpy.context.active_object
body.name = "RookBody"

# Создать основание (тор)
bpy.ops.mesh.primitive_torus_add(
    major_radius=0.6,
    minor_radius=0.15,
    major_segments=32,
    minor_segments=16,
    location=(0, 0, 0.15)
)
base = bpy.context.active_object
base.name = "RookBase"

# Создать верхнее кольцо
bpy.ops.mesh.primitive_cylinder_add(
    vertices=32,
    radius=0.55,
    depth=0.2,
    location=(0, 0, 2.1)
)
top_ring = bpy.context.active_object
top_ring.name = "TopRing"

# Создать зубцы (battlements) на верху
for i in range(4):
    angle = i * (math.pi / 2)
    x = 0.45 * math.cos(angle)
    y = 0.45 * math.sin(angle)
    bpy.ops.mesh.primitive_cube_add(size=0.15, location=(x, y, 2.3))
    tooth = bpy.context.active_object
    tooth.name = f"Tooth_{i}"

# Объединить все детали в одну mesh
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
base.select_set(True)
top_ring.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()

# Поднять модель на Y (для лучшего рендера)
body.location = (0, 0, 0)

# Материал (мрамор)
mat = bpy.data.materials.new(name="Marble")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs['Base Color'].default_value = (0.95, 0.95, 0.9, 1)
bsdf.inputs['Roughness'].default_value = 0.2
body.data.materials.append(mat)

# Камера
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam
cam.location = (3, -3, 2)
cam.rotation_euler = (1.1, 0, 0.78)

# Освещение
light = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", type='SUN'))
bpy.context.collection.objects.link(light)
light.location = (2, 2, 5)

# Рендер
scene = bpy.context.scene
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024
scene.render.filepath = "/tmp/rook_render.png"
bpy.ops.render.render(write_file=True)
```

---

## 📦 Что нужно для запуска на твоём сервере

| Компонент | Требования | Комментарий |
|-----------|-----------|-------------|
| **Blender** | `sudo apt install blender` | Бесплатно, headless работает |
| **LLM** | BlenderLLM (Qwen-Coder-7B) | Можно через API HuggingFace, или скачать (~15GB) |
| **Ollama** | `curl -fsSL https://ollama.com/install.sh \| sh` | Для локального запуска 7B модели |
| **GPU** | Нет! Нужен CPU | CYCLES на CPU, рендер медленнее но работает |
| **RAM** | 8-16GB | Для Qwen-7B нужно ~8-10GB |

---

## 💡 Почему это идеально для тебя

| Проблема | Решение BlenderLLM |
|----------|-------------------|
| Большие модели не тянутся | Это **7B модель** — можно на CPU или Ollama |
| Тяжёлые diffusion-модели | **Нет diffusion** — просто пишем Python-код |
| API цены (Meshy $5/мес) | **Бесплатно** — open-source модель |
| Нужен GPU для 3D | **Нет** — Blender рендерит сцены, а не нейросеть |
| Интерактивный loop | **Есть** — Vision LLM → feedback → доработка кода |
| Контроль результатов | **100%** — ты видишь код перед запуском |

---

## 🔗 References

- **BlenderLLM:** https://github.com/FreedomIntelligence/BlenderLLM
- **LL3M (retired):** https://github.com/threedle/ll3m
- **BlenderLM:** https://github.com/victordibia/blenderlm
- **BlendNet dataset:** https://huggingface.co/datasets/FreedomIntelligence/BlendNet
- **HuggingFace BlenderLLM weights:** https://huggingface.co/FreedomIntelligence/BlenderLLM

---

*Generated by slider-1 | 2026-05-12*
