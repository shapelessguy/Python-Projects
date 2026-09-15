declare module "react-plotly.js/factory" {
  import type { ComponentType } from "react";
  import type { PlotParams } from "react-plotly.js";
  const factory: (plotly: unknown) => ComponentType<PlotParams>;
  export default factory;
}

declare module "plotly.js-dist-min";
