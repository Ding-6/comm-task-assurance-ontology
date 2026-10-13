/**
 * ECharts 按需引入封装
 * - 仅注册用到的图表与组件：折线/柱状/提示/网格/图例/标记线
 * - 用法：const echart = useEcharts(domRef.value); echart.setOption({...});
 */
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, TitleComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  CanvasRenderer,
]);

export function createChart(dom) { return echarts.init(dom); }
export default echarts;