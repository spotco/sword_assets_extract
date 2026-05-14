(function () {
  const canvas = document.getElementById("levelCanvas");
  const ctx = canvas.getContext("2d");
  const summary = document.getElementById("summary");
  const selection = document.getElementById("selection");
  const status = document.getElementById("status");
  const showLabels = document.getElementById("showLabels");
  const showMeshes = document.getElementById("showMeshes");
  const showColliders = document.getElementById("showColliders");
  const showEnter = document.getElementById("showEnter");
  const showNoEnter = document.getElementById("showNoEnter");
  const resetView = document.getElementById("resetView");

  const params = new URLSearchParams(window.location.search);
  const mapName = params.get("map") || "stage_city-ca-da00101";
  const dataUrl = params.get("data") || `/extracted/web_levels/${mapName}/grid.json`;
  const collidersUrl = params.get("colliders") || dataUrl.replace(/grid\.json(?:\?.*)?$/, "colliders.json");
  const meshesUrl = params.get("meshes") || dataUrl.replace(/grid\.json(?:\?.*)?$/, "meshes.json");

  const state = {
    data: null,
    colliders: null,
    meshes: null,
    projected: [],
    selected: null,
    hovered: null,
    scale: 36,
    rotation: Math.PI / 4,
    offsetX: 0,
    offsetY: 0,
    dragMode: null,
    movedDuringDrag: false,
    renderQueued: false,
    meshInstances: [],
    lastMouse: { x: 0, y: 0 },
  };

  const colors = {
    enter: "#4fae88",
    noenter: "#b95d5d",
    "enter-grass": "#6ea65d",
    unknown: "#b99b52",
    selected: "#f4d35e",
    hover: "#f7f1d0",
    meshFill: "rgba(151, 169, 178, 0.2)",
    meshStroke: "rgba(218, 229, 234, 0.18)",
    collider: "rgba(245, 211, 94, 0.68)",
    colliderFill: "rgba(245, 211, 94, 0.08)",
    edge: "rgba(12, 17, 20, 0.7)",
    label: "#101417",
  };

  function setStatus(text) {
    status.textContent = text;
  }

  function setDefinitionList(node, rows) {
    node.replaceChildren();
    for (const [key, value] of rows) {
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = key;
      dd.textContent = value == null || value === "" ? "-" : String(value);
      node.append(dt, dd);
    }
  }

  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * ratio));
    canvas.height = Math.max(1, Math.floor(rect.height * ratio));
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    requestDraw();
  }

  function project(pos) {
    const center = state.data.stats.extent.center;
    const x = pos.x - center.x;
    const z = pos.z - center.z;
    const y = pos.y - center.y;
    const cos = Math.cos(state.rotation);
    const sin = Math.sin(state.rotation);
    const rx = x * cos - z * sin;
    const rz = x * sin + z * cos;
    return {
      x: (rx - rz) * state.scale + state.offsetX,
      y: (rx + rz) * state.scale * 0.5 - y * state.scale * 0.9 + state.offsetY,
    };
  }

  function viewDepth(pos) {
    const center = state.data.stats.extent.center;
    const x = pos.x - center.x;
    const z = pos.z - center.z;
    const y = pos.y - center.y;
    const cos = Math.cos(state.rotation);
    const sin = Math.sin(state.rotation);
    const rx = x * cos - z * sin;
    const rz = x * sin + z * cos;
    return (rx + rz) * 0.9 + y;
  }

  function tileCorners(tile) {
    const position = tile.position;
    const half = 0.42;
    return [
      { x: position.x - half, y: position.y, z: position.z - half },
      { x: position.x + half, y: position.y, z: position.z - half },
      { x: position.x + half, y: position.y, z: position.z + half },
      { x: position.x - half, y: position.y, z: position.z + half },
    ];
  }

  function tilePolygon(tile) {
    return tileCorners(tile).map(project);
  }

  function colliderPosition(collider) {
    if (!collider.position) return null;
    const center = collider.center || { x: 0, y: 0, z: 0 };
    return {
      x: collider.position.x + (center.x || 0),
      y: collider.position.y + (center.y || 0),
      z: collider.position.z + (center.z || 0),
    };
  }

  function colliderPolygons(collider) {
    const position = colliderPosition(collider);
    const size = collider.size;
    if (!position || !size) return null;

    const sx = Math.max(0.08, Math.abs(size.x || 0.08));
    const sy = Math.max(0.08, Math.abs(size.y || 0.08));
    const sz = Math.max(0.08, Math.abs(size.z || 0.08));
    const minX = position.x - sx / 2;
    const maxX = position.x + sx / 2;
    const minY = position.y - sy / 2;
    const maxY = position.y + sy / 2;
    const minZ = position.z - sz / 2;
    const maxZ = position.z + sz / 2;

    return {
      top: [
        project({ x: minX, y: maxY, z: minZ }),
        project({ x: maxX, y: maxY, z: minZ }),
        project({ x: maxX, y: maxY, z: maxZ }),
        project({ x: minX, y: maxY, z: maxZ }),
      ],
      bottom: [
        project({ x: minX, y: minY, z: minZ }),
        project({ x: maxX, y: minY, z: minZ }),
        project({ x: maxX, y: minY, z: maxZ }),
        project({ x: minX, y: minY, z: maxZ }),
      ],
    };
  }

  function pointInPolygon(point, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const xi = polygon[i].x;
      const yi = polygon[i].y;
      const xj = polygon[j].x;
      const yj = polygon[j].y;
      const intersects = yi > point.y !== yj > point.y && point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi;
      if (intersects) inside = !inside;
    }
    return inside;
  }

  function isVisible(tile) {
    if (tile.walkability === "enter" || tile.walkability === "enter-grass") {
      return showEnter.checked;
    }
    if (tile.walkability === "noenter") {
      return showNoEnter.checked;
    }
    return true;
  }

  function colorFor(tile) {
    return colors[tile.walkability] || colors.unknown;
  }

  function drawPolygon(poly, fill, stroke, lineWidth) {
    ctx.beginPath();
    ctx.moveTo(poly[0].x, poly[0].y);
    for (let i = 1; i < poly.length; i += 1) {
      ctx.lineTo(poly[i].x, poly[i].y);
    }
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }

  function strokePath(points) {
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i += 1) {
      ctx.lineTo(points[i].x, points[i].y);
    }
    ctx.stroke();
  }

  function drawColliders() {
    if (!showColliders.checked || !state.colliders) return;

    ctx.strokeStyle = colors.collider;
    ctx.fillStyle = colors.colliderFill;
    ctx.lineWidth = 1.5;
    for (const collider of state.colliders.colliders || []) {
      if (collider.type !== "BoxCollider" || collider.enabled === "False") continue;
      const polys = colliderPolygons(collider);
      if (!polys) continue;

      ctx.beginPath();
      ctx.moveTo(polys.top[0].x, polys.top[0].y);
      for (let i = 1; i < polys.top.length; i += 1) {
        ctx.lineTo(polys.top[i].x, polys.top[i].y);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      strokePath([polys.top[0], polys.bottom[0]]);
      strokePath([polys.top[1], polys.bottom[1]]);
      strokePath([polys.top[2], polys.bottom[2]]);
      strokePath([polys.top[3], polys.bottom[3]]);

      ctx.beginPath();
      ctx.moveTo(polys.bottom[0].x, polys.bottom[0].y);
      for (let i = 1; i < polys.bottom.length; i += 1) {
        ctx.lineTo(polys.bottom[i].x, polys.bottom[i].y);
      }
      ctx.closePath();
      ctx.stroke();
    }
  }

  function drawMeshes() {
    if (!showMeshes.checked || !state.meshInstances.length) return;

    const rect = canvas.getBoundingClientRect();
    const triangleCount = state.meshes.stats.triangleCount || 0;
    const targetTriangles = state.scale < 12 ? 2500 : state.scale < 20 ? 7000 : 24000;
    const stride = Math.max(1, Math.ceil(triangleCount / targetTriangles));
    const pad = 80;

    ctx.fillStyle = colors.meshFill;
    ctx.strokeStyle = colors.meshStroke;
    ctx.lineWidth = 0.75;

    for (const instance of state.meshInstances) {
      const bounds = instance.bounds;
      const corners = [
        { x: bounds.min.x, y: bounds.min.y, z: bounds.min.z },
        { x: bounds.min.x, y: bounds.min.y, z: bounds.max.z },
        { x: bounds.max.x, y: bounds.min.y, z: bounds.min.z },
        { x: bounds.max.x, y: bounds.min.y, z: bounds.max.z },
        { x: bounds.min.x, y: bounds.max.y, z: bounds.min.z },
        { x: bounds.min.x, y: bounds.max.y, z: bounds.max.z },
        { x: bounds.max.x, y: bounds.max.y, z: bounds.min.z },
        { x: bounds.max.x, y: bounds.max.y, z: bounds.max.z },
      ].map(project);
      const instanceMinX = Math.min(...corners.map((point) => point.x));
      const instanceMaxX = Math.max(...corners.map((point) => point.x));
      const instanceMinY = Math.min(...corners.map((point) => point.y));
      const instanceMaxY = Math.max(...corners.map((point) => point.y));
      if (instanceMaxX < -pad || instanceMinX > rect.width + pad || instanceMaxY < -pad || instanceMinY > rect.height + pad) {
        continue;
      }

      const vertices = instance.vertices;
      const indices = instance.indices;
      for (let i = 0, triangleIndex = 0; i < indices.length; i += 3, triangleIndex += 1) {
        if (triangleIndex % stride !== 0) continue;
        const ai = indices[i] * 3;
        const bi = indices[i + 1] * 3;
        const ci = indices[i + 2] * 3;
        const a = project({ x: vertices[ai], y: vertices[ai + 1], z: vertices[ai + 2] });
        const b = project({ x: vertices[bi], y: vertices[bi + 1], z: vertices[bi + 2] });
        const c = project({ x: vertices[ci], y: vertices[ci + 1], z: vertices[ci + 2] });

        const minX = Math.min(a.x, b.x, c.x);
        const maxX = Math.max(a.x, b.x, c.x);
        const minY = Math.min(a.y, b.y, c.y);
        const maxY = Math.max(a.y, b.y, c.y);
        if (maxX < -20 || minX > rect.width + 20 || maxY < -20 || minY > rect.height + 20) {
          continue;
        }

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.lineTo(c.x, c.y);
        ctx.closePath();
        ctx.fill();
        if (state.scale >= 24) {
          ctx.stroke();
        }
      }
    }
  }

  function draw() {
    if (!state.data) return;
    const rect = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);

    drawMeshes();

    state.projected = state.data.tiles
      .filter(isVisible)
      .map((tile) => {
        const poly = tilePolygon(tile);
        const corners = tileCorners(tile);
        return {
          tile,
          poly,
          depth: corners.reduce((sum, point) => sum + viewDepth(point), 0) / corners.length,
        };
      })
      .sort((a, b) => a.depth - b.depth);

    for (const item of state.projected) {
      const fill = colorFor(item.tile);
      const active = item.tile === state.selected || item.tile === state.hovered;
      drawPolygon(item.poly, fill, active ? colors.hover : colors.edge, active ? 2 : 1);

      if (item.tile === state.selected) {
        drawPolygon(item.poly, "rgba(244, 211, 94, 0.28)", colors.selected, 3);
      }

      if (showLabels.checked && state.scale >= 28) {
        const p = project(item.tile.position);
        ctx.fillStyle = colors.label;
        ctx.font = "11px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(item.tile.blockType), p.x, p.y);
      }
    }
    drawColliders();
  }

  function requestDraw() {
    if (state.renderQueued) return;
    state.renderQueued = true;
    window.requestAnimationFrame(() => {
      state.renderQueued = false;
      draw();
    });
  }

  function screenPoint(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  }

  function pick(point) {
    for (let i = state.projected.length - 1; i >= 0; i -= 1) {
      if (pointInPolygon(point, state.projected[i].poly)) {
        return state.projected[i].tile;
      }
    }
    return null;
  }

  function updateSelection(tile) {
    state.selected = tile;
    if (!tile) {
      setDefinitionList(selection, [["Tile", "None"]]);
      requestDraw();
      return;
    }
    const p = tile.position;
    const c = tile.collider || {};
    setDefinitionList(selection, [
      ["Name", tile.name],
      ["Position", `${p.x}, ${p.y}, ${p.z}`],
      ["Walk", tile.walkability],
      ["Type", tile.blockType],
      ["Layer", tile.layer],
      ["Collider", c.type],
      ["Trigger", c.isTrigger],
      ["Path", tile.path],
    ]);
    requestDraw();
  }

  function resetCamera() {
    const rect = canvas.getBoundingClientRect();
    state.scale = Math.max(22, Math.min(44, Math.min(rect.width, rect.height) / 18));
    state.rotation = Math.PI / 4;
    state.offsetX = rect.width / 2;
    state.offsetY = rect.height / 2;
    requestDraw();
  }

  function updateSummary() {
    const data = state.data;
    const metadata = data.metadata || {};
    const mapTool = metadata.mapTool || {};
    const extent = data.stats.extent;
    const colliderStats = state.colliders ? state.colliders.stats : null;
    const meshStats = state.meshes ? state.meshes.stats : null;
    setDefinitionList(summary, [
      ["Map", data.mapName],
      ["Bundle", metadata.bundle],
      ["Tiles", data.stats.tileCount],
      ["Colliders", colliderStats ? `${colliderStats.colliderCount} (${colliderStats.drawableCount} drawable)` : "Not loaded"],
      ["Meshes", meshStats ? `${meshStats.meshInstanceCount} (${meshStats.triangleCount} tris)` : "Not loaded"],
      ["Size", mapTool.width && mapTool.height ? `${mapTool.width} x ${mapTool.height}` : "-"],
      ["Walk", JSON.stringify(data.stats.walkabilityCounts)],
      ["Min", `${extent.min.x}, ${extent.min.y}, ${extent.min.z}`],
      ["Max", `${extent.max.x}, ${extent.max.y}, ${extent.max.z}`],
    ]);
  }

  function initialize(data) {
    state.data = data;
    updateSummary();
    setDefinitionList(selection, [["Tile", "None"]]);
    resetCamera();
    setStatus(`Loaded ${data.stats.tileCount} tiles from ${dataUrl}. Drag to pan, right-drag to rotate.`);
  }

  function initializeColliders(data) {
    state.colliders = data;
    updateSummary();
    requestDraw();
    setStatus(`Loaded ${state.data.stats.tileCount} tiles and ${data.stats.colliderCount} colliders. Right-drag rotates.`);
  }

  function prepareMeshInstances(data) {
    return (data.instances || []).map((instance) => {
      const vertices = instance.vertices || [];
      const xs = [];
      const ys = [];
      const zs = [];
      for (let i = 0; i < vertices.length; i += 3) {
        xs.push(vertices[i]);
        ys.push(vertices[i + 1]);
        zs.push(vertices[i + 2]);
      }
      return {
        vertices,
        indices: instance.indices || [],
        bounds: {
          min: { x: Math.min(...xs), y: Math.min(...ys), z: Math.min(...zs) },
          max: { x: Math.max(...xs), y: Math.max(...ys), z: Math.max(...zs) },
        },
      };
    });
  }

  function initializeMeshes(data) {
    state.meshes = data;
    state.meshInstances = prepareMeshInstances(data);
    updateSummary();
    requestDraw();
    setStatus(`Loaded ${state.data.stats.tileCount} tiles and ${data.stats.meshInstanceCount} mesh instances. Right-drag rotates.`);
  }

  canvas.addEventListener("mousedown", (event) => {
    event.preventDefault();
    state.dragMode = event.button === 2 ? "rotate" : "pan";
    state.movedDuringDrag = false;
    state.lastMouse = screenPoint(event);
    canvas.classList.toggle("panning", state.dragMode === "pan");
    canvas.classList.toggle("rotating", state.dragMode === "rotate");
  });

  window.addEventListener("mouseup", () => {
    state.dragMode = null;
    canvas.classList.remove("panning", "rotating");
  });

  canvas.addEventListener("mousemove", (event) => {
    const point = screenPoint(event);
    if (state.dragMode) {
      const dx = point.x - state.lastMouse.x;
      const dy = point.y - state.lastMouse.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) {
        state.movedDuringDrag = true;
      }
      if (state.dragMode === "rotate") {
        state.rotation += dx * 0.008;
      } else {
        state.offsetX += dx;
        state.offsetY += dy;
      }
      state.lastMouse = point;
      requestDraw();
      return;
    }
    const hovered = pick(point);
    if (hovered !== state.hovered) {
      state.hovered = hovered;
      requestDraw();
    }
  });

  canvas.addEventListener("click", (event) => {
    if (event.button !== 0 || state.movedDuringDrag) return;
    updateSelection(pick(screenPoint(event)));
  });

  canvas.addEventListener("contextmenu", (event) => {
    event.preventDefault();
  });

  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const point = screenPoint(event);
    const oldScale = state.scale;
    const factor = event.deltaY < 0 ? 1.12 : 0.88;
    state.scale = Math.max(8, Math.min(120, state.scale * factor));
    const ratio = state.scale / oldScale;
    state.offsetX = point.x - (point.x - state.offsetX) * ratio;
    state.offsetY = point.y - (point.y - state.offsetY) * ratio;
    requestDraw();
  }, { passive: false });

  showLabels.addEventListener("change", requestDraw);
  showMeshes.addEventListener("change", requestDraw);
  showColliders.addEventListener("change", requestDraw);
  showEnter.addEventListener("change", requestDraw);
  showNoEnter.addEventListener("change", requestDraw);
  resetView.addEventListener("click", resetCamera);
  window.addEventListener("resize", resizeCanvas);

  resizeCanvas();

  function loadOptionalJson(url, handler, label) {
    return fetch(url)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`${response.status} ${response.statusText}`);
        }
        return response.json();
      })
      .then(handler)
      .catch((error) => {
        setStatus(`${label} unavailable from ${url}: ${error.message}`);
      });
  }

  fetch(dataUrl)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return response.json();
    })
    .then(initialize)
    .then(() => Promise.all([
      loadOptionalJson(collidersUrl, initializeColliders, "Collider overlay"),
      loadOptionalJson(meshesUrl, initializeMeshes, "Mesh layer"),
    ]))
    .catch((error) => {
      setStatus(`Could not load ${dataUrl}: ${error.message}`);
    });
})();
