/**
 * ==========================================================================
 * 3D 背景レジストリ
 *
 * #stage[data-bg3d] が設定されている動画でだけ読み込まれる。
 * app.js が window.__bg3d.create() を呼び、GSAP タイムラインの onUpdate から
 * render(t) を叩く。
 *
 * ── 決定性について（ここが最重要） ─────────────────────────
 * hyperframes はタイムラインを時刻 T へ seek してからフレームを捕獲する。
 * 同じ T で必ず同じ絵にならないと、コマ送りがちらつく動画になる。
 * そのため、この中の描画は「時刻 T の純関数」でなければならない。
 *
 *   - requestAnimationFrame を使わない（捕獲クロックと同期しない）
 *   - Date.now() / performance.now() を使わない
 *   - Math.random() を使わない。粒子の初期配置も含めて禁止。
 *     生成のたびに配置が変われば、2 回書き出した動画が別物になる
 *     （検証で最初に踏んだのがここ）。乱数は必ず下の rng() を使う
 *
 * ── 見た目について ────────────────────────────────────
 * 塗りを使わず、点と線だけで描く。3D の階調とノイズは H.264 の圧縮効率を
 * 大きく下げるため（先行検証では陰影のある立体で 46 倍になった）、
 * 平坦な絵にして増加を抑える。実測では 3D なしに対し 1.7〜3.6 倍。
 *
 * 新しいシーンを足すときは、必ず 6 秒の動画を書き出してサイズを測ること。
 * 動く細線がいちばん効く（wave_mesh は分割数を 34 から 12 に落として
 * 13.4 倍 → 3.6 倍になった）。
 *
 * ── Three.js のバージョン ─────────────────────────────
 * r149 に固定している。UMD ビルドは r150 で非推奨、r160 で削除された。
 * 本プロジェクトは ES Modules を使っていないため r149 が使える最終版。
 * 上げるなら ES Modules への移行が前提になる。
 * ==========================================================================
 */
(function () {
  "use strict";

  if (typeof THREE === "undefined") {
    console.warn("[bg3d] Three.js が読み込まれていません。3D 背景は出ません。");
    return;
  }

  // ------------------------------------------------------------------
  // 決定的な擬似乱数（mulberry32）
  //
  // シードが同じなら必ず同じ列を返す。初期配置をこれで作ることで、
  // 何度書き出しても同じ絵になる。
  // ------------------------------------------------------------------
  function makeRng(seed) {
    let a = seed >>> 0;
    return function rng() {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // 動画ごとに配置を変えたいが、同じ動画では必ず同じにしたい。
  // コンポジション ID（動画 ID）から種を作る。
  function seedFrom(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  // ------------------------------------------------------------------
  // シーンの作り方
  //
  // 各シーンは { objects, render(t) } を返す。
  // render は「時刻 t（秒）における姿勢」を決めるだけで、描画自体は
  // 呼び出し側（create）がまとめて行う。
  // ------------------------------------------------------------------

  /** 浮遊する粒子。最も主張が弱く、どの配色にも馴染む。 */
  function buildParticles(ctx) {
    const rng = makeRng(ctx.seed);
    const COUNT = 420;
    const SPREAD = 28;          // 配置する立方体の一辺
    const positions = new Float32Array(COUNT * 3);
    // 粒ごとの漂う速さ。ここも乱数なので rng から採る
    const drift = new Float32Array(COUNT);
    for (let i = 0; i < COUNT; i++) {
      positions[i * 3] = (rng() - 0.5) * SPREAD;
      positions[i * 3 + 1] = (rng() - 0.5) * SPREAD * 0.6;
      positions[i * 3 + 2] = (rng() - 0.5) * SPREAD;
      drift[i] = 0.25 + rng() * 0.5;
    }
    const base = positions.slice();

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const mat = new THREE.PointsMaterial({
      color: ctx.color,
      size: 0.13,
      transparent: true,
      opacity: 0.75,
      // 距離で小さくしない。手前の粒だけ大きくなると階調が増えて圧縮に不利
      sizeAttenuation: true,
    });
    const points = new THREE.Points(geo, mat);

    return {
      objects: [points],
      render(t) {
        // 上下にゆっくり漂わせる。位置は t の関数なので seek しても一意
        for (let i = 0; i < COUNT; i++) {
          positions[i * 3 + 1] = base[i * 3 + 1] + Math.sin(t * drift[i] * 0.35 + i) * 0.7;
        }
        geo.attributes.position.needsUpdate = true;
        points.rotation.y = t * 0.012;
      },
    };
  }

  /** 緩やかに波打つ格子。奥行きが出るので、図解の背景に敷くと画面が締まる。
   *
   * 分割数は控えめにしてある。動く細線は H.264 が最も苦手とする絵で、
   * 34 分割（約 2,400 本）では 6 秒の動画が 14.8MB（3D なしの 13 倍）になった。
   * 16 分割まで落として不透明度も下げると、見た目をほぼ保ったまま収まる。 */
  function buildWaveMesh(ctx) {
    const SEG = 12;             // 一辺の分割数。増やすとファイルサイズが急に効く
    const SIZE = 40;
    const geo = new THREE.PlaneGeometry(SIZE, SIZE, SEG, SEG);
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position;
    const base = Float32Array.from(pos.array);

    const mat = new THREE.MeshBasicMaterial({
      color: ctx.color,
      wireframe: true,
      transparent: true,
      // 背景との差を小さくするほど圧縮が効く。主張させたい層でもないので薄く。
      opacity: 0.16,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.y = -6;

    return {
      objects: [mesh],
      render(t) {
        for (let i = 0; i < pos.count; i++) {
          const x = base[i * 3];
          const z = base[i * 3 + 2];
          // 2 方向のサインを重ねるだけ。周期が違うので単調に見えない
          // 振幅を抑えると、1 フレームあたりの線の移動量が減って
          // フレーム間予測が効く。見た目の「うねり」は十分残る。
          pos.array[i * 3 + 1] =
            Math.sin(x * 0.22 + t * 0.28) * 0.8 +
            Math.cos(z * 0.17 - t * 0.18) * 0.6;
        }
        pos.needsUpdate = true;
      },
    };
  }

  /** 傾いた輪がゆっくり回る。中心に視線を集めたいときに向く。 */
  function buildOrbitRings(ctx) {
    const rng = makeRng(ctx.seed);
    const group = new THREE.Group();
    const RINGS = 5;
    const tilts = [];
    for (let i = 0; i < RINGS; i++) {
      const radius = 5 + i * 2.6;
      // 輪は線で描く。塗ると階調が増えてファイルサイズに効く
      const geo = new THREE.RingGeometry(radius, radius + 0.015, 128);
      const mat = new THREE.MeshBasicMaterial({
        color: ctx.color,
        transparent: true,
        opacity: 0.4 - i * 0.05,
        side: THREE.DoubleSide,
      });
      const ring = new THREE.Mesh(geo, mat);
      ring.rotation.x = Math.PI / 2 + (rng() - 0.5) * 0.7;
      ring.rotation.y = (rng() - 0.5) * 0.7;
      tilts.push({ ring, speed: (i % 2 === 0 ? 1 : -1) * (0.035 + rng() * 0.03) });
      group.add(ring);
    }
    return {
      objects: [group],
      render(t) {
        for (const { ring, speed } of tilts) {
          ring.rotation.z = t * speed;
        }
        group.rotation.y = t * 0.02;
      },
    };
  }

  const SCENES = {
    particles: buildParticles,
    wave_mesh: buildWaveMesh,
    orbit_rings: buildOrbitRings,
  };

  // ------------------------------------------------------------------
  // 公開 API
  // ------------------------------------------------------------------
  window.__bg3d = {
    /** 使えるシーン ID の一覧（画面側の選択肢と突き合わせる用） */
    ids: Object.keys(SCENES),

    /**
     * 3D 背景を作る。
     *
     * @param {string} id      シーン ID（SCENES のキー）
     * @param {HTMLCanvasElement} canvas 描画先
     * @param {object} opts    { width, height, color, seedText }
     * @returns {{render:(t:number)=>void, resize:(w:number,h:number)=>void, dispose:()=>void}|null}
     */
    create(id, canvas, opts) {
      const build = SCENES[id];
      if (!build) {
        console.warn(`[bg3d] 未知の 3D 背景です: ${id}`);
        return null;
      }

      const width = opts.width || 1920;
      const height = opts.height || 1080;

      let renderer;
      try {
        renderer = new THREE.WebGLRenderer({
          canvas: canvas,
          alpha: true,          // 背景色は CSS 側（テーマ）に任せる
          antialias: true,
          // 捕獲方式によっては描画直後にバッファが破棄されることがある。
          // 保持させておかないと、黒いコマが混じる形で非決定になりうる。
          preserveDrawingBuffer: true,
        });
      } catch (e) {
        console.warn("[bg3d] WebGL を初期化できませんでした。3D 背景は出ません。", e);
        return null;
      }
      // 端末の DPR に追従させない。DPR が違うと解像度が変わり、
      // 環境をまたいで同じ絵にならなくなる。
      renderer.setPixelRatio(1);
      renderer.setSize(width, height, false);
      renderer.setClearColor(0x000000, 0);

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 200);
      camera.position.set(0, 2.2, 18);
      camera.lookAt(0, 0, 0);

      const built = build({
        color: new THREE.Color(opts.color || "#6366f1"),
        seed: seedFrom(String(opts.seedText || id)),
      });
      built.objects.forEach((o) => scene.add(o));

      return {
        render(t) {
          built.render(t);
          renderer.render(scene, camera);
        },
        resize(w, h) {
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h, false);
        },
        dispose() {
          renderer.dispose();
        },
      };
    },
  };
})();
