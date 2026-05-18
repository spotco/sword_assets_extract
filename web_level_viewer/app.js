import * as THREE from "./vendor/three.module.js";

const canvas = document.getElementById("levelCanvas");
const summary = document.getElementById("summary");
const selection = document.getElementById("selection");
const meshSelection = document.getElementById("meshSelection");
const meshMaterials = document.getElementById("meshMaterials");
const status = document.getElementById("status");
const renderStats = document.getElementById("renderStats");
const levelCount = document.getElementById("levelCount");
const levelList = document.getElementById("levelList");
const refreshLevelIndex = document.getElementById("refreshLevelIndex");
const showLabels = document.getElementById("showLabels");
const showMeshes = document.getElementById("showMeshes");
const showTextured = document.getElementById("showTextured");
const showColliders = document.getElementById("showColliders");
const showEnter = document.getElementById("showEnter");
const showNoEnter = document.getElementById("showNoEnter");
const resetView = document.getElementById("resetView");
const hideSelectedMesh = document.getElementById("hideSelectedMesh");
const showAllMeshes = document.getElementById("showAllMeshes");
const extractModal = document.getElementById("extractModal");
const extractModalMap = document.getElementById("extractModalMap");
const extractLog = document.getElementById("extractLog");
const extractModalStatus = document.getElementById("extractModalStatus");
const extractClose = document.getElementById("extractClose");
const meshTooltip = document.getElementById("meshTooltip");

function trimSlashes(value, side) {
  if (!value) return "";
  if (side === "start") return value.replace(/^\/+/, "");
  if (side === "end") return value.replace(/\/+$/, "");
  return value.replace(/^\/+|\/+$/g, "");
}

function joinConfiguredUrl(base, path) {
  const cleanBase = trimSlashes(base, "end");
  const cleanPath = trimSlashes(path, "start");
  return cleanBase ? `${cleanBase}/${cleanPath}` : `/${cleanPath}`;
}

function parseBooleanFlag(value) {
  return String(value || "").toLowerCase() === "true";
}

const params = new URLSearchParams(window.location.search);
const pageConfig = document.documentElement.dataset;
const levelRoot = trimSlashes(params.get("levelRoot") || pageConfig.levelRoot || "../extracted/web_levels", "end");
const apiRoot = trimSlashes(params.get("apiRoot") || pageConfig.apiRoot || "..", "end");
const staticMode = parseBooleanFlag(params.get("static")) || parseBooleanFlag(pageConfig.staticSite);
const apiEnabled = !staticMode;
const mapName = params.get("map") || "stage_city-ca-da00101";
const dataUrl = params.get("data") || joinConfiguredUrl(levelRoot, `${mapName}/grid.json`);
const collidersUrl = params.get("colliders") || dataUrl.replace(/grid\.json(?:\?.*)?$/, "colliders.json");
const meshesUrl = params.get("meshes") || dataUrl.replace(/grid\.json(?:\?.*)?$/, "meshes.json");
const materialsUrl = params.get("materials") || dataUrl.replace(/grid\.json(?:\?.*)?$/, "materials.json");
const levelIndexUrl = params.get("index") || joinConfiguredUrl(levelRoot, "index.json");

const state = {
  data: null,
  colliders: null,
  meshes: null,
  exportTransform: null,
  selected: null,
  selectedMesh: null,
  hovered: null,
  hoveredMesh: null,
  lastLoggedMeshId: null,
  yaw: Math.PI / 4,
  pitch: THREE.MathUtils.degToRad(58),
  distance: 42,
  cameraUp: new THREE.Vector3(0, 1, 0),
  zoom: 28,
  target: new THREE.Vector3(0, 0, 0),
  dragMode: null,
  movedDuringDrag: false,
  lastMouse: { x: 0, y: 0 },
  renderQueued: false,
  movementQueued: false,
  lastMovementTime: 0,
  keys: new Set(),
  tileMeshes: [],
  tileLabels: [],
  colliderObjects: [],
  meshObjects: [],
  wireObjects: [],
  hiddenMeshCount: 0,
  materialById: {},
  texturedMaterialCache: {},
  textureLoadStats: { total: 0, loaded: 0, failed: 0 },
  levelIndex: null,
};

const colors = {
  enter: 0x4fae88,
  noenter: 0xb95d5d,
  "enter-grass": 0x6ea65d,
  unknown: 0xb99b52,
  selected: 0xd0845f,
  hover: 0xf4d35e,
  mesh: 0x9bacb5,
  collider: 0xf4d35e,
  edge: 0x20292f,
  label: "#101417",
};

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setClearColor(0x1b2025, 1);
renderer.info.autoReset = false;

const scene = new THREE.Scene();
const world = new THREE.Group();
const meshGroup = new THREE.Group();
const gridGroup = new THREE.Group();
const colliderGroup = new THREE.Group();
const labelGroup = new THREE.Group();
scene.add(world);
world.add(meshGroup, gridGroup, colliderGroup, labelGroup);

const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.01, 1000);
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

const tileMaterials = {
  enter: new THREE.MeshBasicMaterial({ color: colors.enter, side: THREE.DoubleSide }),
  noenter: new THREE.MeshBasicMaterial({ color: colors.noenter, side: THREE.DoubleSide }),
  "enter-grass": new THREE.MeshBasicMaterial({ color: colors["enter-grass"], side: THREE.DoubleSide }),
  unknown: new THREE.MeshBasicMaterial({ color: colors.unknown, side: THREE.DoubleSide }),
};
const selectedMaterial = new THREE.MeshBasicMaterial({ color: colors.selected, side: THREE.DoubleSide });
const hoverMaterial = new THREE.MeshBasicMaterial({ color: colors.hover, side: THREE.DoubleSide });
const edgeMaterial = new THREE.LineBasicMaterial({ color: colors.edge, transparent: true, opacity: 0.95 });
const meshMaterial = new THREE.MeshBasicMaterial({
  color: colors.mesh,
  transparent: true,
  opacity: 0.28,
  depthWrite: false,
  side: THREE.DoubleSide,
});
const meshWireMaterial = new THREE.LineBasicMaterial({ color: 0xd8e4e8, transparent: true, opacity: 0.2 });
const selectedMeshWireMaterial = new THREE.LineBasicMaterial({ color: 0xffd166, transparent: true, opacity: 0.95 });
const selectedMeshGlowMaterial = new THREE.MeshBasicMaterial({
  color: 0xffd166,
  transparent: true,
  opacity: 0.16,
  depthWrite: false,
  side: THREE.BackSide,
  blending: THREE.AdditiveBlending,
});
const colliderMaterial = new THREE.LineBasicMaterial({ color: colors.collider, transparent: true, opacity: 0.72 });

function setStatus(text) {
  status.textContent = text;
}

function setDefinitionList(node, rows) {
  node.replaceChildren();
  for (const [key, value] of rows) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    if (value instanceof Node) {
      dd.append(value);
    } else {
      dd.textContent = value == null || value === "" ? "-" : String(value);
    }
    node.append(dt, dd);
  }
}

function identityExportTransform() {
  const axisX = new THREE.Vector3(1, 0, 0);
  const axisY = new THREE.Vector3(0, 1, 0);
  const axisZ = new THREE.Vector3(0, 0, 1);
  return {
    axisX,
    axisY,
    axisZ,
    matrix: new THREE.Matrix4().makeBasis(axisX, axisY, axisZ),
  };
}

function exportTransformFromPayload(payload) {
  const basis = payload?.metadata?.exportFrame?.basis || payload?.exportFrame?.basis;
  if (!basis) return identityExportTransform();
  const axisX = new THREE.Vector3(basis.right?.x ?? 1, basis.up?.x ?? 0, basis.forward?.x ?? 0).normalize();
  const axisY = new THREE.Vector3(basis.right?.y ?? 0, basis.up?.y ?? 1, basis.forward?.y ?? 0).normalize();
  const axisZ = new THREE.Vector3(basis.right?.z ?? 0, basis.up?.z ?? 0, basis.forward?.z ?? 1).normalize();
  return {
    axisX,
    axisY,
    axisZ,
    matrix: new THREE.Matrix4().makeBasis(axisX, axisY, axisZ),
  };
}

function sourceYOffset(amount) {
  return (state.exportTransform || identityExportTransform()).axisY.clone().multiplyScalar(amount);
}

function tileGeometryForExport() {
  const geometry = new THREE.PlaneGeometry(0.84, 0.84);
  geometry.rotateX(-Math.PI / 2);
  geometry.applyMatrix4((state.exportTransform || identityExportTransform()).matrix);
  return geometry;
}

function boxGeometryForExport(width, height, depth) {
  const geometry = new THREE.BoxGeometry(width, height, depth);
  geometry.applyMatrix4((state.exportTransform || identityExportTransform()).matrix);
  return geometry;
}

function mapUrl(levelMapName) {
  const next = new URL(window.location.href);
  next.searchParams.set("map", levelMapName);
  next.searchParams.delete("data");
  next.searchParams.delete("colliders");
  next.searchParams.delete("meshes");
  next.searchParams.delete("materials");
  return next.toString();
}

function renderLevelMenu(index) {
  state.levelIndex = index;
  levelList.replaceChildren();
  levelCount.textContent = `${index.extractedCount} / ${index.levelCount} extracted`;

  const extracted = (index.levels || []).filter((l) => l.isExtracted);
  const unextracted = (index.levels || []).filter((l) => !l.isExtracted);
  let activeLevelButton = null;

  // If the current map isn't extracted, redirect to the first extracted one
  if (extracted.length > 0 && !extracted.some((l) => l.mapName === mapName)) {
    window.location.href = mapUrl(extracted[0].mapName);
    return;
  }

  for (const level of extracted) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = [
      "level-item",
      "is-extracted",
      level.mapName === mapName ? "is-active" : "",
    ].filter(Boolean).join(" ");
    button.textContent = level.mapName;
    button.title = level.bundle;
    button.addEventListener("click", () => {
      if (level.mapName !== mapName) window.location.href = mapUrl(level.mapName);
    });
    levelList.append(button);
    if (level.mapName === mapName) activeLevelButton = button;
  }

  if (unextracted.length > 0 && apiEnabled) {
    const sep = document.createElement("div");
    sep.className = "level-list-sep";
    sep.textContent = "Not extracted";
    levelList.append(sep);

    for (const level of unextracted) {
      const row = document.createElement("div");
      row.className = "level-item--unextracted";

      const nameSpan = document.createElement("span");
      nameSpan.className = "level-item__name";
      nameSpan.textContent = level.mapName;
      nameSpan.title = level.bundle;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "level-extract-btn";
      btn.textContent = "Extract";
      btn.addEventListener("click", () => runExtraction(level.mapName));

      row.append(nameSpan, btn);
      levelList.append(row);
    }
  }

  if (activeLevelButton) {
    window.requestAnimationFrame(() => {
      activeLevelButton.scrollIntoView({ block: "nearest" });
    });
  }
}

function appendExtractLog(text, type) {
  const line = document.createElement("div");
  line.className = type === "error" ? "log-line log-error" : "log-line";
  line.textContent = text;
  extractLog.append(line);
  extractLog.scrollTop = extractLog.scrollHeight;
}

async function runExtraction(targetMap) {
  if (!apiEnabled) {
    extractModalMap.textContent = targetMap;
    extractLog.replaceChildren();
    appendExtractLog("Extraction is only available from the local development server.", "error");
    extractModalStatus.textContent = "Unavailable";
    extractClose.disabled = false;
    extractModal.hidden = false;
    return;
  }
  extractModalMap.textContent = targetMap;
  extractLog.replaceChildren();
  extractModalStatus.textContent = "Running\u2026";
  extractClose.disabled = true;
  extractModal.hidden = false;

  let response;
  try {
    response = await fetch(joinConfiguredUrl(apiRoot, `api/extract?map=${encodeURIComponent(targetMap)}`), { method: "POST" });
  } catch (err) {
    appendExtractLog(`Network error: ${err.message}`, "error");
    appendExtractLog("Is server.py running? (python server.py)", "error");
    extractModalStatus.textContent = "Failed";
    extractClose.disabled = false;
    return;
  }

  if (!response.ok) {
    appendExtractLog(`Server error: ${response.status} ${response.statusText}`, "error");
    extractModalStatus.textContent = "Failed";
    extractClose.disabled = false;
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  const processSSE = (text) => {
    buf += text;
    const blocks = buf.split("\n\n");
    buf = blocks.pop();
    for (const block of blocks) {
      if (!block.trim()) continue;
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) {
          try { data = JSON.parse(line.slice(6)); } catch { data = line.slice(6); }
        }
      }
      if (event === "log") appendExtractLog(data);
      else if (event === "done") {
        extractModalStatus.textContent = "Done \u2713";
        extractClose.disabled = false;
        loadLevelIndex();
      } else if (event === "error") {
        appendExtractLog(data, "error");
        extractModalStatus.textContent = "Failed";
        extractClose.disabled = false;
      }
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      processSSE(decoder.decode(value, { stream: true }));
    }
  } catch (err) {
    appendExtractLog(`Stream error: ${err.message}`, "error");
    extractModalStatus.textContent = "Failed";
    extractClose.disabled = false;
  }
}

function renderFallbackLevelMenu() {
  levelList.replaceChildren();
  levelCount.textContent = "Index missing";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "level-item is-extracted is-active";
  button.textContent = mapName;
  button.title = "Current map";
  levelList.append(button);
}

function applyMeshMaterials() {
  const useTextured = showTextured.checked && hasReadyTexturedMaterials();
  for (const mesh of state.meshObjects) {
    if (useTextured) {
      const materials = mesh.userData.materialIds.map((matId) => materialForMeshId(matId) || meshMaterial);
      if (materials.some((material) => material !== meshMaterial)) {
        mesh.material = materials.length === 1 ? materials[0] : materials;
      } else {
        mesh.material = meshMaterial;
      }
    } else {
      mesh.material = meshMaterial;
    }
  }
  for (const wire of state.wireObjects) {
    wire.visible = !useTextured;
  }
  syncSelectedMeshVisuals();
  requestDraw();
}

function materialForMeshId(matId) {
  const matRecord = matId ? state.materialById[matId] : null;
  if (!matRecord?._textureReady) return null;
  const tex = matRecord?._texture ?? null;
  if (!tex) return null;
  if (!state.texturedMaterialCache[matId]) {
    state.texturedMaterialCache[matId] = new THREE.MeshBasicMaterial({
      map: tex,
      side: THREE.DoubleSide,
    });
  }
  return state.texturedMaterialCache[matId];
}

function hasReadyTexturedMaterials() {
  return Object.values(state.materialById).some((mat) => mat._textureReady);
}

function loadTextureWithRetry(loader, url, onLoad, onError, onTexture, attempt = 1) {
  const texture = loader.load(url, onLoad, undefined, (err) => {
    if (attempt < 3) {
      window.setTimeout(() => {
        loadTextureWithRetry(loader, url, onLoad, onError, onTexture, attempt + 1);
      }, 250 * attempt);
      return;
    }
    onError(err);
  });
  texture.colorSpace = THREE.SRGBColorSpace;
  onTexture(texture);
  return texture;
}

function initializeMaterials(data) {
  state.materialById = {};
  state.textureLoadStats = { total: 0, loaded: 0, failed: 0 };
  const loader = new THREE.TextureLoader();
  for (const mat of data.materials || []) {
    const record = { ...mat, _texture: null, _textureReady: false, _textureError: null };
    state.materialById[mat.id] = record;
    if (mat.mainTexture?.path) {
      const texUrl = materialsUrl.replace(/materials\.json.*$/, mat.mainTexture.path);
      state.textureLoadStats.total += 1;
      loadTextureWithRetry(
        loader,
        texUrl,
        () => {
          if (!record._textureReady) {
            record._textureReady = true;
            state.textureLoadStats.loaded += 1;
          }
          if (showTextured.checked) applyMeshMaterials();
          updateSummary();
        },
        (err) => {
          const record = state.materialById[mat.id];
          if (record) record._textureError = err?.message || String(err);
          state.textureLoadStats.failed += 1;
          logViewerEvent("texture-load-error", {
            mapName,
            materialId: mat.id,
            materialName: mat.name,
            texturePath: mat.mainTexture.path,
            error: err?.message || String(err),
          });
          if (showTextured.checked) applyMeshMaterials();
          updateSummary();
        },
        (texture) => {
          record._texture = texture;
        },
      );
    }
  }
  applyMeshMaterials();
  if (state.selectedMesh) updateSelectedMesh(state.selectedMesh);
  if (state.data) updateSummary();
}

function materialForTile(tile) {
  return tileMaterials[tile.walkability] || tileMaterials.unknown;
}

function screenPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
}

function updateCamera() {
  const horizontal = Math.cos(state.pitch) * state.distance;
  camera.position.set(
    state.target.x + Math.sin(state.yaw) * horizontal,
    state.target.y + Math.sin(state.pitch) * state.distance,
    state.target.z + Math.cos(state.yaw) * horizontal,
  );
  camera.up.copy(state.cameraUp);
  camera.lookAt(state.target);
  camera.updateMatrixWorld();
}

function resizeRenderer() {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, rect.width);
  const height = Math.max(1, rect.height);
  const ratio = width / height;
  const halfHeight = state.zoom / 2;
  camera.left = -halfHeight * ratio;
  camera.right = halfHeight * ratio;
  camera.top = halfHeight;
  camera.bottom = -halfHeight;
  camera.updateProjectionMatrix();
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height, false);
  requestDraw();
}

function requestDraw() {
  if (state.renderQueued) return;
  state.renderQueued = true;
  window.requestAnimationFrame(draw);
}

function requestMovement() {
  if (state.movementQueued) return;
  state.movementQueued = true;
  state.lastMovementTime = performance.now();
  window.requestAnimationFrame(updateMovement);
}

function updateMovement(now) {
  const elapsed = Math.min(0.05, Math.max(0, (now - state.lastMovementTime) / 1000));
  state.lastMovementTime = now;

  let right = 0;
  let zoomDirection = 0;
  let vertical = 0;
  if (state.keys.has("a") || state.keys.has("arrowleft")) right -= 1;
  if (state.keys.has("d") || state.keys.has("arrowright")) right += 1;
  if (state.keys.has("w") || state.keys.has("arrowup")) zoomDirection -= 1;
  if (state.keys.has("s") || state.keys.has("arrowdown")) zoomDirection += 1;
  if (state.keys.has("q")) vertical += 1;
  if (state.keys.has("e")) vertical -= 1;

  if (right || zoomDirection || vertical) {
    const length = Math.hypot(right, zoomDirection, vertical) || 1;
    const speed = state.zoom * 0.85;
    moveCameraByView((right / length) * speed * elapsed, 0);
    if (vertical) {
      state.target.y += (vertical / length) * speed * elapsed;
    }
    if (zoomDirection) {
      const zoomSpeed = state.zoom * 1.75;
      state.zoom = THREE.MathUtils.clamp(state.zoom + (zoomDirection / length) * zoomSpeed * elapsed, 5, 120);
      resizeRenderer();
    }
    requestDraw();
    window.requestAnimationFrame(updateMovement);
    return;
  }

  state.movementQueued = false;
}

function draw() {
  state.renderQueued = false;
  updateCamera();
  meshGroup.visible = showMeshes.checked;
  colliderGroup.visible = showColliders.checked;
  labelGroup.visible = showLabels.checked && state.zoom <= 26;
  updateMeshVisibility();
  for (const mesh of state.tileMeshes) {
    const walkability = mesh.userData.tile.walkability;
    mesh.visible =
      walkability === "enter" || walkability === "enter-grass"
        ? showEnter.checked
        : walkability === "noenter"
          ? showNoEnter.checked
          : true;
  }

  renderer.info.reset();
  renderer.render(scene, camera);
  renderStats.textContent = `${renderer.info.render.triangles.toLocaleString()} polygons`;
}

function clearGroup(group) {
  for (const child of [...group.children]) {
    group.remove(child);
    if (child.geometry) child.geometry.dispose();
    if (child.material && !Array.isArray(child.material)) {
      const shared = [
        selectedMaterial,
        hoverMaterial,
        edgeMaterial,
        meshMaterial,
        meshWireMaterial,
        selectedMeshWireMaterial,
        selectedMeshGlowMaterial,
        colliderMaterial,
        ...Object.values(tileMaterials),
      ].includes(child.material);
      if (!shared) child.material.dispose();
    }
  }
  if (group === meshGroup) {
    for (const mat of Object.values(state.texturedMaterialCache)) mat.dispose();
    state.texturedMaterialCache = {};
    state.wireObjects = [];
  }
}

function makeTileLabel(text) {
  const canvas2d = document.createElement("canvas");
  canvas2d.width = 64;
  canvas2d.height = 64;
  const ctx = canvas2d.getContext("2d");
  ctx.fillStyle = colors.label;
  ctx.font = "bold 28px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(text), 32, 34);
  const texture = new THREE.CanvasTexture(canvas2d);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(0.45, 0.45, 0.45);
  return sprite;
}

function addTile(tile) {
  const geometry = tileGeometryForExport();
  const mesh = new THREE.Mesh(geometry, materialForTile(tile));
  mesh.position.set(tile.position.x, tile.position.y, tile.position.z);
  mesh.position.add(sourceYOffset(0.035));
  mesh.userData.tile = tile;
  mesh.renderOrder = 20;
  gridGroup.add(mesh);
  state.tileMeshes.push(mesh);

  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), edgeMaterial);
  edges.position.copy(mesh.position);
  edges.renderOrder = 21;
  gridGroup.add(edges);

  const label = makeTileLabel(tile.blockType);
  label.position.set(tile.position.x, tile.position.y, tile.position.z);
  label.position.add(sourceYOffset(0.08));
  label.renderOrder = 30;
  labelGroup.add(label);
  state.tileLabels.push(label);
}

function buildGrid(data) {
  clearGroup(gridGroup);
  clearGroup(labelGroup);
  state.tileMeshes = [];
  state.tileLabels = [];
  for (const tile of data.tiles || []) {
    addTile(tile);
  }
}

function buildMeshes(data) {
  clearGroup(meshGroup);
  state.meshObjects = [];
  state.wireObjects = [];
  state.selectedMesh = null;
  state.hiddenMeshCount = 0;
  updateSelectedMesh(null);
  updateHiddenMeshControls();
  for (const instance of data.instances || []) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(instance.vertices || [], 3));
    if (instance.uvs && instance.uvs.length > 0) {
      geometry.setAttribute("uv", new THREE.Float32BufferAttribute(instance.uvs, 2));
    }
    geometry.setIndex(instance.indices || []);
    for (const submesh of instance.submeshes || []) {
      const start = Number(submesh.start || 0);
      const count = Number(submesh.triangleCount || 0) * 3;
      const materialIndex = Math.max(0, instance.materialIds.indexOf(String(submesh.materialId ?? "")));
      if (count > 0) geometry.addGroup(start, count, materialIndex);
    }
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();

    const mesh = new THREE.Mesh(geometry, meshMaterial);
    mesh.renderOrder = 1;
    mesh.userData.materialIds = instance.materialIds || [];
    mesh.userData.instance = instance;
    mesh.userData.hidden = false;
    meshGroup.add(mesh);
    state.meshObjects.push(mesh);

    const wire = new THREE.LineSegments(new THREE.WireframeGeometry(geometry), meshWireMaterial);
    wire.renderOrder = 2;
    wire.userData.instance = instance;
    wire.userData.mesh = mesh;
    mesh.userData.wire = wire;
    meshGroup.add(wire);
    state.wireObjects.push(wire);

    const glow = new THREE.Mesh(geometry, selectedMeshGlowMaterial);
    glow.renderOrder = 3;
    glow.scale.setScalar(1.02);
    glow.visible = false;
    glow.userData.mesh = mesh;
    mesh.userData.glow = glow;
    meshGroup.add(glow);
  }
  syncSelectedMeshVisuals();
}

function colliderPosition(collider) {
  if (!collider.position) return null;
  const center = collider.center || { x: 0, y: 0, z: 0 };
  return new THREE.Vector3(
    collider.position.x + (center.x || 0),
    collider.position.y + (center.y || 0),
    collider.position.z + (center.z || 0),
  );
}

function buildColliders(data) {
  clearGroup(colliderGroup);
  state.colliderObjects = [];
  for (const collider of data.colliders || []) {
    if (collider.type !== "BoxCollider" || collider.enabled === "False" || !collider.size) continue;
    const position = colliderPosition(collider);
    if (!position) continue;
    const geometry = boxGeometryForExport(
      Math.max(0.08, Math.abs(collider.size.x || 0.08)),
      Math.max(0.08, Math.abs(collider.size.y || 0.08)),
      Math.max(0.08, Math.abs(collider.size.z || 0.08)),
    );
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), colliderMaterial);
    edges.position.copy(position);
    edges.renderOrder = 10;
    colliderGroup.add(edges);
    state.colliderObjects.push(edges);
  }
}

function updateSelection(tile) {
  state.selected = tile;
  for (const mesh of state.tileMeshes) {
    if (mesh.userData.tile === state.selected) {
      mesh.material = selectedMaterial;
    } else if (mesh.userData.tile === state.hovered) {
      mesh.material = hoverMaterial;
    } else {
      mesh.material = materialForTile(mesh.userData.tile);
    }
  }

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

function updateHover(tile) {
  if (tile === state.hovered) return;
  state.hovered = tile;
  updateSelection(state.selected);
}

function updateSelectedMesh(mesh) {
  state.selectedMesh = mesh;
  hideSelectedMesh.disabled = !mesh || mesh.userData.hidden;
  meshMaterials.replaceChildren();
  syncSelectedMeshVisuals();

  if (!mesh) {
    setDefinitionList(meshSelection, [["Mesh", "None"]]);
    requestDraw();
    return;
  }

  const instance = mesh.userData.instance || {};
  const staticBatch = instance.staticBatch || {};
  setDefinitionList(meshSelection, [
    ["Name", instance.name],
    ["Path", instance.path],
    ["Mesh", instance.meshName],
    ["Object ID", instance.id],
    ["Mesh ID", instance.meshId],
    ["Layer", instance.layer],
    ["Coord", instance.coordinateSpace],
    ["Static", `${staticBatch.firstSubMesh ?? 0} + ${staticBatch.subMeshCount ?? 0}`],
    ["Renderer", instance.rendererEnabled],
    ["Vertices", instance.vertexCount],
    ["Triangles", instance.triangleCount],
  ]);
  renderMeshMaterialSlots(instance);
  logViewerEvent("mesh-select", meshDebugPayload(instance));
  requestDraw();
}

function renderMeshMaterialSlots(instance) {
  const submeshes = instance.submeshes || [];
  if (submeshes.length === 0) return;
  for (const submesh of submeshes) {
    const matId = String(submesh.materialId ?? "");
    const mat = matId ? state.materialById[matId] : null;
    const texture = mat?.mainTexture;
    const slot = document.createElement("div");
    slot.className = "mesh-material-slot";

    const title = document.createElement("div");
    title.className = "mesh-material-slot__title";
    title.textContent = `Submesh ${submesh.index} -> material ${matId || "-"}`;

    const meta = document.createElement("div");
    meta.className = "mesh-material-slot__meta";
    meta.textContent = [
      `triangles: ${submesh.triangleCount}`,
      `material: ${mat?.name || "-"}`,
      `shader: ${mat?.shader || "-"}`,
      `texture: ${texture?.name || "-"}`,
      `texturePath: ${texture?.path || "-"}`,
      `textureId: ${texture?.id || "-"}`,
      `slots: ${Object.keys(mat?.textures || {}).join(", ") || "-"}`,
    ].join("\n");

    slot.append(title, meta);
    meshMaterials.append(slot);
  }
}

function updateMeshVisibility() {
  const useTextured = showTextured.checked && hasReadyTexturedMaterials();
  for (const mesh of state.meshObjects) {
    mesh.visible = !mesh.userData.hidden;
    const wire = mesh.userData.wire;
    if (wire) wire.visible = !mesh.userData.hidden && !useTextured;
    const glow = mesh.userData.glow;
    if (glow) glow.visible = false;
  }
  syncSelectedMeshVisuals();
}

function syncSelectedMeshVisuals() {
  const useTextured = showTextured.checked && hasReadyTexturedMaterials();
  for (const mesh of state.meshObjects) {
    const selected = mesh === state.selectedMesh && !mesh.userData.hidden;
    const wire = mesh.userData.wire;
    const glow = mesh.userData.glow;
    if (wire) {
      wire.material = selected ? selectedMeshWireMaterial : meshWireMaterial;
      wire.visible = selected || (!mesh.userData.hidden && !useTextured);
    }
    if (glow) {
      glow.visible = selected;
    }
  }
}

function updateHiddenMeshControls() {
  showAllMeshes.hidden = state.hiddenMeshCount === 0;
  showAllMeshes.textContent = state.hiddenMeshCount > 0
    ? `Show all meshes (${state.hiddenMeshCount})`
    : "Show all meshes";
}

function hideMesh(mesh) {
  if (!mesh || mesh.userData.hidden) return;
  mesh.userData.hidden = true;
  state.hiddenMeshCount += 1;
  if (mesh === state.selectedMesh) hideSelectedMesh.disabled = true;
  updateHiddenMeshControls();
  updateMeshHover(null, { x: 0, y: 0 });
  logViewerEvent("mesh-hide", meshDebugPayload(mesh.userData.instance || {}));
  requestDraw();
}

function showEveryMesh() {
  for (const mesh of state.meshObjects) {
    mesh.userData.hidden = false;
  }
  state.hiddenMeshCount = 0;
  if (state.selectedMesh) hideSelectedMesh.disabled = false;
  updateHiddenMeshControls();
  requestDraw();
}

function updateMeshHover(mesh, point) {
  if (mesh === state.hoveredMesh) {
    positionMeshTooltip(point);
    return;
  }
  state.hoveredMesh = mesh;
  if (!mesh) {
    meshTooltip.hidden = true;
    meshTooltip.replaceChildren();
    return;
  }

  const instance = mesh.userData.instance || {};
  const title = document.createElement("div");
  title.className = "mesh-tooltip__name";
  title.textContent = instance.name || instance.meshName || "Unnamed mesh";
  const meta = document.createElement("div");
  meta.className = "mesh-tooltip__meta";
  meta.textContent = [instance.meshName, instance.path].filter(Boolean).join(" | ");
  meshTooltip.replaceChildren(title, meta);
  meshTooltip.hidden = false;
  positionMeshTooltip(point);

  if (instance.id !== state.lastLoggedMeshId) {
    state.lastLoggedMeshId = instance.id;
    logViewerEvent("mesh-hover", meshDebugPayload(instance));
  }
}

function positionMeshTooltip(point) {
  if (meshTooltip.hidden) return;
  const viewport = canvas.parentElement.getBoundingClientRect();
  const tooltip = meshTooltip.getBoundingClientRect();
  const x = Math.min(point.x + 14, viewport.width - tooltip.width - 10);
  const y = Math.min(point.y + 14, viewport.height - tooltip.height - 10);
  meshTooltip.style.left = `${Math.max(10, x)}px`;
  meshTooltip.style.top = `${Math.max(10, y)}px`;
}

function pickTile(point) {
  const rect = canvas.getBoundingClientRect();
  mouse.x = (point.x / rect.width) * 2 - 1;
  mouse.y = -(point.y / rect.height) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(state.tileMeshes.filter((mesh) => mesh.visible), false);
  return hits.length ? hits[0].object.userData.tile : null;
}

function pickMesh(point) {
  if (!showMeshes.checked) return null;
  const rect = canvas.getBoundingClientRect();
  mouse.x = (point.x / rect.width) * 2 - 1;
  mouse.y = -(point.y / rect.height) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(state.meshObjects.filter((mesh) => mesh.visible && !mesh.userData.hidden), false);
  return hits.length ? hits[0].object : null;
}

function zoomByWheelDirection(deltaY) {
  const factor = deltaY < 0 ? 0.88 : 1.12;
  state.zoom = THREE.MathUtils.clamp(state.zoom * factor, 5, 120);
  resizeRenderer();
}

function meshDebugPayload(instance) {
  const materialIds = instance.materialIds || [];
  return {
    mapName,
    id: instance.id,
    name: instance.name,
    path: instance.path,
    meshId: instance.meshId,
    meshName: instance.meshName,
    coordinateSpace: instance.coordinateSpace,
    staticBatch: instance.staticBatch,
    vertexCount: instance.vertexCount,
    triangleCount: instance.triangleCount,
    materialIds,
    materials: materialIds.map((matId) => {
      const mat = state.materialById[matId];
      return mat ? {
        id: mat.id,
        name: mat.name,
        shader: mat.shader,
        mainTexture: mat.mainTexture,
        textureSlots: Object.keys(mat.textures || {}),
      } : { id: matId, missing: true };
    }),
    submeshes: instance.submeshes,
    textured: showTextured.checked,
  };
}

function logViewerEvent(event, details) {
  if (!apiEnabled) return;
  fetch(joinConfiguredUrl(apiRoot, "api/view-log"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, details }),
    keepalive: true,
  }).catch(() => {});
}

function panByPixels(dx, dy) {
  const rect = canvas.getBoundingClientRect();
  const worldPerPixel = state.zoom / Math.max(1, rect.height);
  const right = new THREE.Vector3();
  const up = new THREE.Vector3();
  camera.updateMatrixWorld();
  camera.matrixWorld.extractBasis(right, up, new THREE.Vector3());
  state.target.addScaledVector(right, -dx * worldPerPixel);
  state.target.addScaledVector(up, dy * worldPerPixel);
}

function moveCameraByView(rightAmount, forwardAmount) {
  const right = new THREE.Vector3();
  const up = new THREE.Vector3();
  const backward = new THREE.Vector3();
  camera.updateMatrixWorld();
  camera.matrixWorld.extractBasis(right, up, backward);
  const forward = backward.negate();
  state.target.addScaledVector(right, rightAmount);
  state.target.addScaledVector(forward, forwardAmount);
}

function resetCamera() {
  const center = state.data?.stats?.extent?.center || { x: 0, y: 0, z: 0 };
  state.target.set(center.x, center.y, center.z);
  const defaultCamera = state.data?.metadata?.defaultCamera;
  const forward = defaultCamera?.forward;
  if (forward && Number.isFinite(forward.x) && Number.isFinite(forward.y) && Number.isFinite(forward.z)) {
    const back = new THREE.Vector3(-forward.x, -forward.y, -forward.z).normalize();
    const up = defaultCamera.up
      ? new THREE.Vector3(defaultCamera.up.x, defaultCamera.up.y, defaultCamera.up.z).normalize()
      : new THREE.Vector3(0, 1, 0);
    const horizontal = Math.hypot(back.x, back.z);
    state.yaw = Math.atan2(back.x, back.z);
    state.pitch = Math.atan2(back.y, horizontal);
    state.cameraUp.copy(up);
    state.distance = Math.max(20, Math.hypot(
      center.x - (defaultCamera.position?.x ?? center.x),
      center.y - (defaultCamera.position?.y ?? center.y),
      center.z - (defaultCamera.position?.z ?? center.z),
    ));
    state.zoom = defaultCamera.orthographicSize > 0 ? defaultCamera.orthographicSize * 2 : 24;
  } else {
    state.yaw = Math.PI / 4;
    state.pitch = THREE.MathUtils.degToRad(58);
    state.cameraUp.set(0, 1, 0);
    state.zoom = 24;
  }
  resizeRenderer();
}

function updateSummary() {
  const data = state.data;
  const metadata = data.metadata || {};
  const mapTool = metadata.mapTool || {};
  const extent = data.stats.extent;
  const colliderStats = state.colliders ? state.colliders.stats : null;
  const meshStats = state.meshes ? state.meshes.stats : null;
  const matStats = Object.keys(state.materialById).length > 0
    ? `${Object.keys(state.materialById).length} materials (${state.textureLoadStats.loaded}/${state.textureLoadStats.total} textures)`
    : "Not loaded";
  setDefinitionList(summary, [
    ["Map", data.mapName],
    ["Bundle", metadata.bundle],
    ["Tiles", data.stats.tileCount],
    ["Colliders", colliderStats ? `${colliderStats.colliderCount} (${colliderStats.drawableCount} drawable)` : "Not loaded"],
    ["Meshes", meshStats ? `${meshStats.meshInstanceCount} (${meshStats.triangleCount} tris)` : "Not loaded"],
    ["Materials", matStats],
    ["Size", mapTool.width && mapTool.height ? `${mapTool.width} x ${mapTool.height}` : "-"],
    ["Walk", JSON.stringify(data.stats.walkabilityCounts)],
    ["Min", `${extent.min.x}, ${extent.min.y}, ${extent.min.z}`],
    ["Max", `${extent.max.x}, ${extent.max.y}, ${extent.max.z}`],
  ]);
}

function initialize(data) {
  state.data = data;
  state.exportTransform = exportTransformFromPayload(data);
  buildGrid(data);
  updateSummary();
  setDefinitionList(selection, [["Tile", "None"]]);
  setDefinitionList(meshSelection, [["Mesh", "None"]]);
  meshMaterials.replaceChildren();
  resetCamera();
  setStatus(`Loaded ${data.stats.tileCount} tiles from ${dataUrl}. Left-drag pans. Right-drag rotates. W/S or arrows zoom.`);
}

function initializeMissingLevel(error) {
  setDefinitionList(summary, [
    ["Map", mapName],
    ["Status", "Not extracted"],
    ["Grid", error.message],
  ]);
  setDefinitionList(selection, [["Tile", "None"]]);
  setDefinitionList(meshSelection, [["Mesh", "None"]]);
  meshMaterials.replaceChildren();
  setStatus(
    apiEnabled
      ? `No extracted data for ${mapName}. Use Extract in the map list, or run the export pipeline.`
      : `No packaged data for ${mapName}. Rebuild the static bundle to include this map.`,
  );
}

function initializeColliders(data) {
  state.colliders = data;
  buildColliders(data);
  updateSummary();
  requestDraw();
  setStatus(`Loaded ${state.data.stats.tileCount} tiles and ${data.stats.colliderCount} colliders. Right-drag rotates.`);
}

function initializeMeshes(data) {
  state.meshes = data;
  buildMeshes(data);
  applyMeshMaterials();
  updateSummary();
  setStatus(`Loaded ${state.data.stats.tileCount} tiles and ${data.stats.meshInstanceCount} mesh instances. Click a mesh for material slots.`);
}

function loadOptionalJson(url, handler, label) {
  return fetch(url)
    .then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response.json();
    })
    .then(handler)
    .catch((error) => {
      setStatus(`${label} unavailable from ${url}: ${error.message}`);
    });
}

function loadLevelIndex() {
  return fetch(levelIndexUrl, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response.json();
    })
    .then(renderLevelMenu)
    .catch(() => {
      renderFallbackLevelMenu();
    });
}

async function refreshLevelIndexList() {
  refreshLevelIndex.disabled = true;
  levelCount.textContent = apiEnabled ? "Extracting map list..." : "Refreshing map list...";
  try {
    let response = apiEnabled
      ? await fetch(joinConfiguredUrl(apiRoot, "api/level-index"), { method: "POST" })
      : await fetch(`${levelIndexUrl}?cb=${Date.now()}`, { cache: "no-store" });
    if (apiEnabled && response.status === 404) {
      response = await fetch(`${levelIndexUrl}?cb=${Date.now()}`, { cache: "no-store" });
    }
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const index = await response.json();
    renderLevelMenu(index);
  } catch (error) {
    levelCount.textContent = `Map list failed: ${error.message}`;
  } finally {
    refreshLevelIndex.disabled = false;
  }
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
    updateMeshHover(null, point);
    const dx = point.x - state.lastMouse.x;
    const dy = point.y - state.lastMouse.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) state.movedDuringDrag = true;
    if (state.dragMode === "rotate") {
      state.yaw -= dx * 0.008;
      state.pitch = THREE.MathUtils.clamp(state.pitch + dy * 0.006, THREE.MathUtils.degToRad(-85), THREE.MathUtils.degToRad(85));
    } else {
      panByPixels(dx, dy);
    }
    state.lastMouse = point;
    requestDraw();
    return;
  }
  updateHover(pickTile(point));
  updateMeshHover(pickMesh(point), point);
});

canvas.addEventListener("click", (event) => {
  if (event.button !== 0 || state.movedDuringDrag) return;
  const point = screenPoint(event);
  const mesh = pickMesh(point);
  updateSelectedMesh(mesh);
  updateSelection(mesh ? null : pickTile(point));
});

canvas.addEventListener("contextmenu", (event) => {
  event.preventDefault();
});

window.addEventListener("keydown", (event) => {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  const key = event.key.toLowerCase();
  if (!["w", "a", "s", "d", "q", "e", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(key)) return;
  event.preventDefault();
  state.keys.add(key);
  requestMovement();
});

window.addEventListener("keyup", (event) => {
  state.keys.delete(event.key.toLowerCase());
});

canvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  zoomByWheelDirection(event.deltaY);
}, { passive: false });

showLabels.addEventListener("change", requestDraw);
showMeshes.addEventListener("change", requestDraw);
showTextured.addEventListener("change", applyMeshMaterials);
showColliders.addEventListener("change", requestDraw);
showEnter.addEventListener("change", requestDraw);
showNoEnter.addEventListener("change", requestDraw);
resetView.addEventListener("click", resetCamera);
hideSelectedMesh.addEventListener("click", () => hideMesh(state.selectedMesh));
showAllMeshes.addEventListener("click", showEveryMesh);
refreshLevelIndex.addEventListener("click", refreshLevelIndexList);
extractClose.addEventListener("click", () => {
  extractModal.hidden = true;
  loadLevelIndex();
});
window.addEventListener("resize", resizeRenderer);

resizeRenderer();
if (!apiEnabled) {
  refreshLevelIndex.textContent = "Reload map list";
}
loadLevelIndex();
fetch(dataUrl)
  .then((response) => {
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  })
  .then(initialize)
  .then(() => Promise.all([
    loadOptionalJson(collidersUrl, initializeColliders, "Collider overlay"),
    loadOptionalJson(meshesUrl, initializeMeshes, "Mesh layer"),
    loadOptionalJson(materialsUrl, initializeMaterials, "Material data"),
  ]))
  .catch((error) => {
    initializeMissingLevel(error);
  });
