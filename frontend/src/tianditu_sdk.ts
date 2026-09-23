export interface TiandituOverlay {
  addEventListener(event: string, handler: () => void): void;
}

export interface TiandituMapInstance {
  addOverLay(overlay: TiandituOverlay): void;
  addEventListener(event: "click", handler: (event: TiandituMapClickEvent) => void): void;
  centerAndZoom(center: TiandituLngLat, zoom: number): void;
  clearOverLays(): void;
  enableScrollWheelZoom(): void;
  removeEventListener(event: "click", handler: (event: TiandituMapClickEvent) => void): void;
  setStyle(style: string): void;
}

export interface TiandituLngLat {
  getLat(): number;
  getLng(): number;
}

export interface TiandituMapClickEvent {
  lnglat: TiandituLngLat;
}

export interface TiandituNamespace {
  Map: new (container: HTMLElement) => TiandituMapInstance;
  LngLat: new (lng: number, lat: number) => TiandituLngLat;
  Label: new (options: { text: string; position: TiandituLngLat }) => TiandituOverlay & {
    setBackgroundColor(color: string): void;
    setBorderColor(color: string): void;
    setBorderLine(width: number): void;
    setFontColor(color: string): void;
    setFontSize(size: number): void;
  };
  Polyline: new (
    points: TiandituLngLat[],
    options?: { color?: string; lineStyle?: "solid" | "dashed"; opacity?: number; weight?: number },
  ) => TiandituOverlay;
}

declare global {
  interface Window {
    T?: TiandituNamespace;
  }
}

const script_id = "tianditu-js-api";
let script_promise: Promise<TiandituNamespace> | null = null;

function ready_namespace(): TiandituNamespace | undefined {
  const api = window.T;
  if (
    api !== undefined
    && typeof api.Map === "function"
    && typeof api.LngLat === "function"
    && typeof api.Label === "function"
    && typeof api.Polyline === "function"
  ) {
    return api;
  }
  return undefined;
}

function wait_for_namespace(resolve: (api: TiandituNamespace) => void, reject: (error: Error) => void) {
  const deadline = Date.now() + 12_000;
  const check = () => {
    const api = ready_namespace();
    if (api !== undefined) {
      resolve(api);
      return;
    }
    if (Date.now() >= deadline) {
      reject(new Error("天地图脚本已加载，但地图覆盖物 API 未就绪"));
      return;
    }
    window.setTimeout(check, 50);
  };
  check();
}

export function load_tianditu(api_key: string): Promise<TiandituNamespace> {
  const ready_api = ready_namespace();
  if (ready_api !== undefined) {
    return Promise.resolve(ready_api);
  }
  if (script_promise !== null) {
    return script_promise;
  }

  const pending = new Promise<TiandituNamespace>((resolve, reject) => {
    const existing = document.getElementById(script_id) as HTMLScriptElement | null;
    const script = existing ?? document.createElement("script");
    script.id = script_id;
    script.async = true;
    script.src = `https://api.tianditu.gov.cn/api?v=4.0&tk=${encodeURIComponent(api_key)}`;
    script.onload = () => wait_for_namespace(resolve, reject);
    script.onerror = () => reject(new Error("天地图脚本加载失败"));
    if (existing === null) {
      document.head.appendChild(script);
    } else {
      wait_for_namespace(resolve, reject);
    }
  });
  const loading = pending.catch((error) => {
    script_promise = null;
    throw error;
  });
  script_promise = loading;
  return loading;
}
