// Only the chart types and components the app uses, so the bundle carries a fraction of ECharts. Loaded on first use
// (dynamic import from EChart.tsx), so pages without charts never download it.
import * as echarts from "echarts/core";
import { BarChart, HeatmapChart, LineChart, SankeyChart, ScatterChart, TreemapChart } from "echarts/charts";
import { DatasetComponent, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([BarChart, HeatmapChart, LineChart, SankeyChart, ScatterChart, TreemapChart, DatasetComponent, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent, CanvasRenderer]);
export { echarts };
