export async function loadSceneMeta(sceneId) {
  const scene = await fetch(`/scenes/${sceneId}/scene.json`)
    .then(r => { if (!r.ok) throw new Error(`scene.json ${r.status}`); return r.json() })
  const objects = await fetch(`/scenes/${sceneId}/objects.json`)
    .then(r => r.ok ? r.json() : [])
    .catch(() => [])
  return { scene, objects }
}
