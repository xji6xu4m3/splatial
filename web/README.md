# web — Splatial Viewer

Vite + Three.js web viewer that loads a Gaussian Splat scene and renders anchored GLB objects in the same coordinate frame.

## Public API

### `createViewer(container, plyUrl) -> Promise<Viewer>`
(`web/src/splatViewer.js`)

Mounts a `@mkkellogg/gaussian-splats-3d` viewer into `container` (DOM element), loads the `.ply` from `plyUrl`, starts the render loop, and returns the viewer instance. Access the underlying Three.js scene via `viewer.threeScene`.

### `loadSceneMeta(sceneId) -> Promise<{ scene, objects }>`
(`web/src/sceneLoader.js`)

Fetches `/scenes/<sceneId>/scene.json` (a `SplatScene`) and `/scenes/<sceneId>/objects.json` (an array of `SceneObject`). Returns `{ scene, objects }`. If `objects.json` is missing or the request fails, `objects` defaults to `[]`.

### `loadGLB(url) -> Promise<THREE.Object3D>`
(`web/src/objects.js`)

Loads a GLB from `url` using `GLTFLoader` and returns `gltf.scene`.

### `applyTransform(obj3d, transform)`
(`web/src/objects.js`)

Sets `position`, `quaternion` (from `[x,y,z,w]`), and `scale` on a `THREE.Object3D` from a `Transform` dict.

### `placeObject(threeScene, sceneObject) -> Promise<THREE.Object3D>`
(`web/src/objects.js`)

Loads the GLB at `sceneObject.glb`, applies `sceneObject.transform`, optionally overrides material color from `sceneObject.material_overrides.color` (`[r,g,b]` 0-1), sets `userData.objectId`, adds to `threeScene`, and returns the root node.

## Shared Data Contracts

The viewer reads JSON produced by the Python `scene_store` module. The shapes are:

```
SplatScene  { "id": str, "ply": "scene.ply", "bbox": [[minx,miny,minz],[maxx,maxy,maxz]],
              "up": [x,y,z], "scale_hint": float, "source_meta": { ... } }

Transform   { "position": [x,y,z], "rotation": [x,y,z,w], "scale": [x,y,z] }

SceneObject { "id": str, "glb": str, "transform": Transform,
              "material_overrides": { "color"?: [r,g,b] }, "scene_id": str }
```

Scene files live at `scenes/<id>/scene.json` and `scenes/<id>/objects.json`. The `.ply` is at `scenes/<id>/scene.ply`.

## Development

```bash
cd web
npm install
npm run dev      # dev server on http://localhost:5173
npm run build    # production bundle (compile check)
```

Open `http://localhost:5173/view/?scene=room1` (the build uses base `/view/`) — the viewer reads `scenes/room1/` via the `../scenes` symlink (`web/scenes -> ../scenes`).

## Smoke Tests

```bash
cd web
npx playwright install chromium
npx playwright test
```

Requires a real `scenes/room1/` with `scene.ply`, `scene.json`, and `objects.json` (from Task 4 + 6). The spec verifies `window.__viewer` is set, at least 1 object is loaded, a `<canvas>` is visible, and there are no console errors.
