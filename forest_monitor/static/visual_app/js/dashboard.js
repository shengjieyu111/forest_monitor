const palette = {
    green: '#3de29f', green2: '#78f0bd', blue: '#4ba7ff', cyan: '#42d6d0',
    amber: '#ffbd5a', coral: '#ff6f6f', violet: '#a77bff', muted: '#6f9185',
    grid: 'rgba(150,210,184,.10)', text: '#91afa4'
};

const charts = {};
let dashboardPayload = null;
let recordPage = 1;
let recordPageCount = 1;
let trendMode = 'environment';

const $ = (id) => document.getElementById(id);
const fmt = (value, digits = 1) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits });
const axisStyle = {
    axisLine: { lineStyle: { color: palette.grid } },
    axisTick: { show: false },
    axisLabel: { color: palette.text, fontSize: 9 },
    splitLine: { lineStyle: { color: palette.grid } }
};

function initChart(id) {
    if (!charts[id]) charts[id] = echarts.init($(id), null, { renderer: 'canvas' });
    return charts[id];
}

function baseTooltip() {
    return {
        trigger: 'axis',
        backgroundColor: 'rgba(6,20,16,.96)',
        borderColor: 'rgba(61,226,159,.25)',
        textStyle: { color: '#dff5e9', fontSize: 11 }
    };
}

async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`请求失败：${response.status}`);
    return response.json();
}

function queryDates() {
    const params = new URLSearchParams();
    if ($('startDate').value) params.set('start_date', $('startDate').value);
    if ($('endDate').value) params.set('end_date', $('endDate').value);
    return params;
}

async function loadDashboard(showLoading = true, forceRefresh = false) {
    if (showLoading) $('loading').classList.remove('hidden');
    try {
        const params = queryDates();
        if (forceRefresh) params.set('refresh', '1');
        const payload = await fetchJson(`/api/dashboard/?${params}`);
        if (payload.empty) throw new Error(payload.message);
        dashboardPayload = payload;
        renderSummary(payload);
        renderAllCharts(payload);
        renderAlerts(payload.alerts);
        await loadRecords(1);
    } catch (error) {
        showToast(error.message);
    } finally {
        $('loading').classList.add('hidden');
    }
}

function renderSummary(data) {
    const { meta, kpis, latest } = data;
    $('cityName').textContent = meta.city;
    $('dateRange').textContent = `${meta.start_date} 至 ${meta.end_date}`;
    $('recordCount').textContent = `${fmt(meta.record_count, 0)} 条记录`;
    $('updatedAt').textContent = `最新统计 ${meta.updated_at}`;
    $('sourceLabel').textContent = data.source.label;
    $('sourcePath').textContent = `HDFS ${meta.source_path}`;
    $('sourceLabel').style.color = data.source.online ? palette.green2 : palette.amber;
    if (!$('startDate').value) $('startDate').value = meta.start_date;
    if (!$('endDate').value) $('endDate').value = meta.end_date;

    $('kpiTemp').textContent = `${fmt(kpis.temperature_avg)} ℃`;
    $('kpiTempMax').textContent = `峰值 ${fmt(kpis.temperature_max)} ℃`;
    $('kpiHumidity').textContent = `${fmt(kpis.humidity_avg)} %`;
    $('kpiPm25').textContent = fmt(kpis.pm25_avg);
    $('kpiLight').textContent = `${fmt(kpis.illumination_max / 1000)}k lx`;
    $('kpiRisk').textContent = fmt(kpis.risk_events, 0);
    $('kpiHighRisk').textContent = `高风险 ${fmt(kpis.high_risk_events, 0)}`;
    $('kpiHealth').textContent = `${fmt(kpis.health_score, 0)} 分`;
    $('kpiRecords').textContent = fmt(meta.record_count, 0);
    $('kpiCurrentRisk').textContent = latest.risk;
    $('kpiCurrentTime').textContent = latest.time;
}

function renderAllCharts(data) {
    renderTrend(data);
    renderGauge(data);
    renderDaily(data);
    renderRisk(data);
    renderRadar(data);
    renderScatter(data);
    renderHourly(data);
    renderDistribution(data);
    renderHeatmap(data);
}

function renderTrend(data) {
    const chart = initChart('trendChart');
    const common = {
        smooth: true, showSymbol: false, emphasis: { focus: 'series' },
        lineStyle: { width: 2 }, areaStyle: { opacity: .08 }
    };
    let series;
    let yAxis;
    if (trendMode === 'air') {
        series = [{ ...common, name: 'PM2.5', type: 'line', data: data.trend.pm25, itemStyle: { color: palette.amber } }];
        yAxis = [{ ...axisStyle, name: 'μg/m³', nameTextStyle: { color: palette.text } }];
    } else if (trendMode === 'light') {
        series = [{ ...common, name: '光照', type: 'line', data: data.trend.illumination, itemStyle: { color: palette.violet } }];
        yAxis = [{ ...axisStyle, name: 'lx', nameTextStyle: { color: palette.text } }];
    } else {
        series = [
            { ...common, name: '温度', type: 'line', data: data.trend.temperature, itemStyle: { color: palette.green } },
            { ...common, name: '湿度', type: 'line', yAxisIndex: 1, data: data.trend.humidity, itemStyle: { color: palette.blue } }
        ];
        yAxis = [
            { ...axisStyle, name: '℃', nameTextStyle: { color: palette.text } },
            { ...axisStyle, name: '%', nameTextStyle: { color: palette.text }, splitLine: { show: false } }
        ];
    }
    chart.setOption({
        animationDuration: 700, tooltip: baseTooltip(),
        legend: { top: 4, textStyle: { color: palette.text, fontSize: 10 } },
        grid: { left: 45, right: 45, top: 45, bottom: 55 },
        dataZoom: [{ type: 'inside' }, { type: 'slider', height: 14, bottom: 12, borderColor: 'transparent', fillerColor: 'rgba(61,226,159,.15)', textStyle: { color: palette.text } }],
        xAxis: { ...axisStyle, type: 'category', data: data.trend.times, boundaryGap: false, axisLabel: { color: palette.text, fontSize: 9, formatter: value => value.slice(5) } },
        yAxis, series
    }, true);
}

function renderGauge(data) {
    initChart('gaugeChart').setOption({
        series: [{
            type: 'gauge', startAngle: 210, endAngle: -30, min: 0, max: 100, radius: '88%',
            progress: { show: true, width: 15, roundCap: true, itemStyle: { color: palette.green } },
            axisLine: { lineStyle: { width: 15, color: [[.45, 'rgba(255,111,111,.25)'], [.75, 'rgba(255,189,90,.25)'], [1, 'rgba(61,226,159,.15)']] } },
            axisTick: { show: false }, splitLine: { show: false },
            axisLabel: { distance: 22, color: palette.text, fontSize: 9 },
            pointer: { width: 4, length: '58%', itemStyle: { color: '#d9fff0' } },
            anchor: { show: true, size: 10, itemStyle: { color: palette.green } },
            title: { offsetCenter: [0, '68%'], color: palette.text, fontSize: 11 },
            detail: { valueAnimation: true, formatter: '{value} 分', color: '#f2fff8', fontSize: 27, offsetCenter: [0, '28%'] },
            data: [{ value: data.kpis.health_score, name: data.latest.risk }]
        }]
    }, true);
}

function renderDaily(data) {
    initChart('dailyChart').setOption({
        tooltip: baseTooltip(),
        legend: { top: 4, textStyle: { color: palette.text, fontSize: 9 } },
        grid: { left: 42, right: 18, top: 45, bottom: 30 },
        xAxis: { ...axisStyle, type: 'category', data: data.daily.map(item => item.date.slice(5)) },
        yAxis: { ...axisStyle, type: 'value', name: '℃', nameTextStyle: { color: palette.text } },
        series: [
            { name: '平均温度', type: 'bar', data: data.daily.map(item => item.temperature_avg), itemStyle: { color: 'rgba(61,226,159,.48)', borderRadius: [4,4,0,0] } },
            { name: '温度峰值', type: 'line', smooth: true, data: data.daily.map(item => item.temperature_max), itemStyle: { color: palette.amber }, lineStyle: { width: 3 } }
        ]
    }, true);
}

function renderRisk(data) {
    const colorMap = { '正常': palette.green, '低风险': palette.blue, '中风险': palette.amber, '高风险': palette.coral };
    initChart('riskChart').setOption({
        tooltip: { ...baseTooltip(), trigger: 'item' },
        legend: { bottom: 0, textStyle: { color: palette.text, fontSize: 9 } },
        series: [{
            type: 'pie', radius: ['48%', '72%'], center: ['50%', '44%'],
            label: { color: '#d9eee5', fontSize: 9, formatter: '{b}\n{d}%' },
            itemStyle: { borderColor: '#0c201a', borderWidth: 3, borderRadius: 6 },
            data: data.risk_distribution.map(item => ({ ...item, itemStyle: { color: colorMap[item.name] } }))
        }]
    }, true);
}

function renderRadar(data) {
    initChart('radarChart').setOption({
        radar: {
            radius: '65%',
            indicator: [
                { name: '温度', max: 40 }, { name: '湿度', max: 100 }, { name: 'PM2.5', max: 100 },
                { name: '光照(k)', max: 100 }, { name: '风险率', max: 100 }
            ],
            axisName: { color: palette.text, fontSize: 9 },
            splitLine: { lineStyle: { color: ['rgba(150,210,184,.08)', 'rgba(150,210,184,.14)'] } },
            splitArea: { areaStyle: { color: ['rgba(61,226,159,.01)', 'rgba(61,226,159,.035)'] } },
            axisLine: { lineStyle: { color: palette.grid } }
        },
        series: [{
            type: 'radar',
            data: [{ value: data.radar.values, name: '综合环境', areaStyle: { color: 'rgba(61,226,159,.24)' }, lineStyle: { color: palette.green }, itemStyle: { color: palette.green } }]
        }]
    }, true);
}

function renderScatter(data) {
    const riskColor = { '正常': palette.green, '低风险': palette.blue, '中风险': palette.amber, '高风险': palette.coral };
    initChart('scatterChart').setOption({
        tooltip: {
            trigger: 'item', backgroundColor: 'rgba(6,20,16,.96)', borderColor: palette.grid,
            formatter: p => `${p.value[3]}<br>温度 ${p.value[0]} ℃<br>湿度 ${p.value[1]} %<br>PM2.5 ${p.value[2]}<br>${p.value[4]}`
        },
        grid: { left: 48, right: 20, top: 20, bottom: 38 },
        xAxis: { ...axisStyle, name: '温度 ℃', nameTextStyle: { color: palette.text } },
        yAxis: { ...axisStyle, name: '湿度 %', nameTextStyle: { color: palette.text } },
        series: [{
            type: 'scatter',
            data: data.scatter,
            symbolSize: value => Math.max(5, Math.min(18, value[2] / 5)),
            itemStyle: { color: p => riskColor[p.value[4]], opacity: .68 }
        }]
    }, true);
}

function renderHourly(data) {
    initChart('hourlyChart').setOption({
        tooltip: baseTooltip(),
        legend: { top: 3, textStyle: { color: palette.text, fontSize: 9 } },
        grid: { left: 42, right: 44, top: 42, bottom: 32 },
        xAxis: { ...axisStyle, type: 'category', data: data.peak_comparison.map(item => item.date.slice(5)), axisLabel: { color: palette.text, fontSize: 9 } },
        yAxis: [
            { ...axisStyle, type: 'value' },
            { ...axisStyle, type: 'value', splitLine: { show: false } }
        ],
        series: [
            { name: '温度峰值', type: 'line', smooth: true, data: data.peak_comparison.map(item => item.temperature), itemStyle: { color: palette.green } },
            { name: '湿度峰值', type: 'line', smooth: true, data: data.peak_comparison.map(item => item.humidity), itemStyle: { color: palette.blue } },
            { name: 'PM2.5峰值', type: 'bar', yAxisIndex: 1, data: data.peak_comparison.map(item => item.pm25), itemStyle: { color: 'rgba(255,189,90,.48)', borderRadius: [3,3,0,0] } }
        ]
    }, true);
}

function renderDistribution(data) {
    initChart('distributionChart').setOption({
        tooltip: { ...baseTooltip(), trigger: 'axis' },
        grid: { left: 48, right: 16, top: 24, bottom: 35 },
        xAxis: { ...axisStyle, type: 'value' },
        yAxis: { ...axisStyle, type: 'category', data: data.temperature_distribution.map(item => item.name) },
        series: [{
            type: 'bar',
            data: data.temperature_distribution.map((item, index) => ({
                value: item.value,
                itemStyle: { color: [palette.blue, palette.cyan, palette.green, palette.amber, palette.coral][index], borderRadius: [0,5,5,0] }
            })),
            label: { show: true, position: 'right', color: '#cce2d8', fontSize: 9 }
        }]
    }, true);
}

function renderHeatmap(data) {
    initChart('heatmapChart').setOption({
        tooltip: { position: 'top', formatter: p => `${data.heatmap_dates[p.value[0]]}<br>${data.heatmap_metrics[p.value[1]]}：${p.value[2]}` },
        grid: { left: 75, right: 22, top: 20, bottom: 55 },
        xAxis: { ...axisStyle, type: 'category', data: data.heatmap_dates.map(date => date.slice(5)), splitArea: { show: true }, axisLabel: { color: palette.text, fontSize: 9 } },
        yAxis: { ...axisStyle, type: 'category', data: data.heatmap_metrics, splitArea: { show: true } },
        visualMap: {
            min: 20, max: 90, calculable: true, orient: 'horizontal', left: 'center', bottom: 2,
            textStyle: { color: palette.text, fontSize: 9 },
            inRange: { color: ['#173a66', '#1d8f83', '#42d391', '#f0bb55', '#eb6767'] }
        },
        series: [{ type: 'heatmap', data: data.heatmap, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,.6)' } } }]
    }, true);
}

function renderAlerts(alerts) {
    const container = $('alertList');
    if (!alerts.length) {
        container.innerHTML = '<div class="empty-state">当前范围内暂无风险预警</div>';
        return;
    }
    container.innerHTML = alerts.map(item => `
        <div class="alert-item ${item.level === '高风险' ? 'high' : ''}">
            <span class="alert-level"></span>
            <div><strong>${item.message}</strong><small>温度 ${item.temperature}℃ · 湿度 ${item.humidity}% · PM2.5 ${item.pm25}</small></div>
            <span class="alert-time">${item.time}</span>
        </div>
    `).join('');
}

async function loadRecords(page = 1) {
    const params = queryDates();
    params.set('page', page);
    params.set('page_size', 15);
    if ($('recordKeyword').value) params.set('keyword', $('recordKeyword').value);
    if ($('riskFilter').value) params.set('risk', $('riskFilter').value);
    const data = await fetchJson(`/api/records/?${params}`);
    recordPage = data.page;
    recordPageCount = data.page_count;
    $('recordsBody').innerHTML = data.results.map(item => {
        const className = { '低风险': 'low', '中风险': 'medium', '高风险': 'high' }[item.risk] || '';
        return `<tr>
            <td>${item.date}</td>
            <td>${item.temperature_avg.toFixed(2)} / ${item.temperature_max.toFixed(1)} ℃</td>
            <td>${item.humidity_avg.toFixed(2)} / ${item.humidity_max.toFixed(1)} %</td>
            <td>${item.pm25_avg.toFixed(2)} / ${item.pm25_max.toFixed(1)}</td>
            <td>${fmt(item.illumination_avg, 0)} / ${fmt(item.illumination_max, 0)} lx</td>
            <td>${item.warning}</td>
            <td><span class="risk-pill ${className}">${item.risk}</span></td>
        </tr>`;
    }).join('') || '<tr><td colspan="7" class="empty-state">没有匹配的记录</td></tr>';
    $('pageInfo').textContent = `共 ${fmt(data.total, 0)} 条记录`;
    $('pageNumber').textContent = `${data.page} / ${data.page_count}`;
    $('prevPage').disabled = data.page <= 1;
    $('nextPage').disabled = data.page >= data.page_count;
}

function showToast(message) {
    const toast = $('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

function bindEvents() {
    $('applyFilter').addEventListener('click', () => loadDashboard(true, true));
    $('resetFilter').addEventListener('click', () => {
        $('startDate').value = '';
        $('endDate').value = '';
        loadDashboard(true, true);
    });
    $('trendMetric').addEventListener('click', event => {
        const button = event.target.closest('button');
        if (!button) return;
        trendMode = button.dataset.metric;
        $('trendMetric').querySelectorAll('button').forEach(item => item.classList.toggle('active', item === button));
        renderTrend(dashboardPayload);
    });
    $('searchRecords').addEventListener('click', () => loadRecords(1));
    $('recordKeyword').addEventListener('keydown', event => { if (event.key === 'Enter') loadRecords(1); });
    $('riskFilter').addEventListener('change', () => loadRecords(1));
    $('prevPage').addEventListener('click', () => loadRecords(recordPage - 1));
    $('nextPage').addEventListener('click', () => loadRecords(recordPage + 1));
    window.addEventListener('resize', () => Object.values(charts).forEach(chart => chart.resize()));
}

function startClock() {
    const tick = () => {
        $('clock').textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    };
    tick();
    setInterval(tick, 1000);
}

document.addEventListener('DOMContentLoaded', () => {
    startClock();
    bindEvents();
    loadDashboard();
});
