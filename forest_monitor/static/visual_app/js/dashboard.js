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
let hdfsPath = '/waether';
let hdfsParentPath = null;
let activeJobId = null;
let jobPollTimer = null;

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

function getCookie(name) {
    return document.cookie.split(';').map(item => item.trim()).find(item => item.startsWith(`${name}=`))?.split('=')[1] || '';
}

async function fetchJson(url, options = {}) {
    const requestOptions = { ...options };
    if (requestOptions.method && requestOptions.method !== 'GET') {
        requestOptions.headers = {
            'X-CSRFToken': decodeURIComponent(getCookie('csrftoken')),
            ...(requestOptions.headers || {})
        };
    }
    const response = await fetch(url, requestOptions);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || payload.message || `请求失败：${response.status}`);
    return payload;
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
    $('sourcePath').textContent = meta.source_path;
    $('sourceLabel').style.color = data.source.online ? palette.green2 : palette.amber;
    if (!$('startDate').value) $('startDate').value = meta.start_date;
    if (!$('endDate').value) $('endDate').value = meta.end_date;

    $('kpiTemp').textContent = `${fmt(kpis.temperature_avg)} ℃`;
    $('kpiTempMax').textContent = `峰值 ${fmt(kpis.temperature_max)} ℃`;
    $('kpiHumidity').textContent = `${fmt(kpis.humidity_avg)} %`;
    $('kpiPm25').textContent = fmt(kpis.pm25_avg);
    $('kpiLight').textContent = `${fmt(kpis.illumination_max / 1000)}k lx`;
    $('kpiRisk').textContent = fmt(kpis.risk_events, 0);
    $('kpiHighRisk').textContent = `样本风险率 ${fmt(kpis.risk_rate)}%`;
    $('kpiHealth').textContent = `${fmt(kpis.health_score, 0)} 分`;
    $('kpiHealth').nextElementSibling.textContent = `舒适率 ${fmt(kpis.comfort_rate)}%`;
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
    renderRiskTrend(data);
    renderComfortTrend(data);
    renderTopN(data);
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
    const totals = data.risk_detail.reduce((result, item) => {
        result[0].value += item.high_temp_count;
        result[1].value += item.high_humidity_count;
        result[2].value += item.pollution_count;
        result[3].value += item.fire_risk_count;
        return result;
    }, [
        { name: '高温样本', value: 0, itemStyle: { color: palette.amber } },
        { name: '高湿样本', value: 0, itemStyle: { color: palette.blue } },
        { name: '污染样本', value: 0, itemStyle: { color: palette.violet } },
        { name: '火险样本', value: 0, itemStyle: { color: palette.coral } }
    ]);
    initChart('riskChart').setOption({
        tooltip: { ...baseTooltip(), trigger: 'item' },
        legend: { bottom: 0, textStyle: { color: palette.text, fontSize: 9 } },
        series: [{
            type: 'pie', radius: ['48%', '72%'], center: ['50%', '44%'],
            label: { color: '#d9eee5', fontSize: 9, formatter: '{b}\n{d}%' },
            itemStyle: { borderColor: '#0c201a', borderWidth: 3, borderRadius: 6 },
            data: totals
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
        xAxis: { ...axisStyle, type: 'category', data: data.hourly.map(item => item.hour), axisLabel: { color: palette.text, fontSize: 9, interval: 2 } },
        yAxis: [
            { ...axisStyle, type: 'value' },
            { ...axisStyle, type: 'value', splitLine: { show: false } }
        ],
        series: [
            { name: '平均温度', type: 'line', smooth: true, data: data.hourly.map(item => item.temperature), itemStyle: { color: palette.green }, showSymbol: false },
            { name: '平均湿度', type: 'line', smooth: true, data: data.hourly.map(item => item.humidity), itemStyle: { color: palette.blue }, showSymbol: false },
            { name: '平均PM2.5', type: 'bar', yAxisIndex: 1, data: data.hourly.map(item => item.pm25), itemStyle: { color: 'rgba(255,189,90,.48)', borderRadius: [3,3,0,0] } }
        ]
    }, true);
}

function renderRiskTrend(data) {
    const rows = data.risk_detail;
    initChart('riskTrendChart').setOption({
        tooltip: baseTooltip(),
        legend: { top: 3, textStyle: { color: palette.text, fontSize: 9 } },
        grid: { left: 46, right: 48, top: 44, bottom: 45 },
        dataZoom: [{ type: 'inside' }, { type: 'slider', height: 12, bottom: 5 }],
        xAxis: { ...axisStyle, type: 'category', data: rows.map(item => item.date.slice(5)) },
        yAxis: [
            { ...axisStyle, type: 'value', name: '样本数', nameTextStyle: { color: palette.text } },
            { ...axisStyle, type: 'value', name: '风险率 %', max: 100, splitLine: { show: false }, nameTextStyle: { color: palette.text } }
        ],
        series: [
            { name: '高温', type: 'bar', stack: 'risk', data: rows.map(item => item.high_temp_count), itemStyle: { color: palette.amber } },
            { name: '高湿', type: 'bar', stack: 'risk', data: rows.map(item => item.high_humidity_count), itemStyle: { color: palette.blue } },
            { name: '污染', type: 'bar', stack: 'risk', data: rows.map(item => item.pollution_count), itemStyle: { color: palette.violet } },
            { name: '火险', type: 'bar', stack: 'risk', data: rows.map(item => item.fire_risk_count), itemStyle: { color: palette.coral } },
            { name: '风险率', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, data: rows.map(item => item.risk_rate), itemStyle: { color: palette.green2 }, lineStyle: { width: 3 } }
        ]
    }, true);
}

function renderComfortTrend(data) {
    const rows = data.comfort_detail;
    initChart('comfortTrendChart').setOption({
        tooltip: baseTooltip(),
        legend: { top: 3, textStyle: { color: palette.text, fontSize: 9 } },
        grid: { left: 46, right: 48, top: 44, bottom: 45 },
        dataZoom: [{ type: 'inside' }, { type: 'slider', height: 12, bottom: 5 }],
        xAxis: { ...axisStyle, type: 'category', data: rows.map(item => item.date.slice(5)) },
        yAxis: [
            { ...axisStyle, type: 'value', name: '样本数', nameTextStyle: { color: palette.text } },
            { ...axisStyle, type: 'value', name: '舒适率 %', max: 100, splitLine: { show: false }, nameTextStyle: { color: palette.text } }
        ],
        series: [
            { name: '舒适', type: 'bar', stack: 'comfort', data: rows.map(item => item.comfortable_count), itemStyle: { color: palette.green } },
            { name: '关注', type: 'bar', stack: 'comfort', data: rows.map(item => item.attention_count), itemStyle: { color: palette.amber } },
            { name: '不适', type: 'bar', stack: 'comfort', data: rows.map(item => item.uncomfortable_count), itemStyle: { color: palette.coral } },
            { name: '舒适率', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, data: rows.map(item => item.comfort_rate), itemStyle: { color: palette.cyan }, lineStyle: { width: 3 } }
        ]
    }, true);
}

function renderTopN(data) {
    const rows = [...data.topn].reverse();
    initChart('topNChart').setOption({
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(6,20,16,.96)',
            borderColor: 'rgba(61,226,159,.25)',
            textStyle: { color: '#dff5e9', fontSize: 11 },
            formatter: params => {
                const item = rows[params[0].dataIndex];
                return [
                    `Top ${item.rank} · ${item.date}`,
                    `风险分：${item.risk_score}`,
                    `危险样本：${item.dangerous_count}`,
                    `温度峰值：${item.temperature_peak} ℃`,
                    `最低湿度：${item.humidity_low} %`,
                    `PM2.5 峰值：${item.pm25_peak}`
                ].join('<br>');
            }
        },
        legend: { top: 3, textStyle: { color: palette.text, fontSize: 9 } },
        grid: { left: 90, right: 60, top: 42, bottom: 28 },
        xAxis: [
            { ...axisStyle, type: 'value', name: '风险分', nameTextStyle: { color: palette.text } },
            { ...axisStyle, type: 'value', name: '危险样本', splitLine: { show: false }, nameTextStyle: { color: palette.text } }
        ],
        yAxis: {
            ...axisStyle,
            type: 'category',
            data: rows.map(item => `Top ${item.rank}  ${item.date}`)
        },
        series: [
            {
                name: '综合风险分',
                type: 'bar',
                data: rows.map(item => item.risk_score),
                itemStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                        { offset: 0, color: palette.amber },
                        { offset: 1, color: palette.coral }
                    ]),
                    borderRadius: [0, 5, 5, 0]
                },
                label: { show: true, position: 'right', color: '#dff5e9', fontSize: 10 }
            },
            {
                name: '危险样本数',
                type: 'line',
                xAxisIndex: 1,
                data: rows.map(item => item.dangerous_count),
                itemStyle: { color: palette.cyan },
                lineStyle: { width: 2 }
            }
        ]
    }, true);
}

function renderDistribution(data) {
    const totals = data.comfort_detail.reduce((result, item) => {
        result[0].value += item.comfortable_count;
        result[1].value += item.attention_count;
        result[2].value += item.uncomfortable_count;
        return result;
    }, [
        { name: '舒适', value: 0 },
        { name: '关注', value: 0 },
        { name: '不适', value: 0 }
    ]);
    initChart('distributionChart').setOption({
        tooltip: { ...baseTooltip(), trigger: 'axis' },
        grid: { left: 48, right: 16, top: 24, bottom: 35 },
        xAxis: { ...axisStyle, type: 'value' },
        yAxis: { ...axisStyle, type: 'category', data: totals.map(item => item.name) },
        series: [{
            type: 'bar',
            data: totals.map((item, index) => ({
                value: item.value,
                itemStyle: { color: [palette.green, palette.amber, palette.coral][index], borderRadius: [0,5,5,0] }
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

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function showSelectedFile(file) {
    if (!file) {
        $('selectedFileName').textContent = '文件将上传到 /waether/input';
        $('selectedFileMeta').textContent = '支持本地文件直接拖拽，无需使用 Windows 搜索';
        return;
    }
    $('selectedFileName').textContent = file.name;
    $('selectedFileMeta').textContent = `${formatBytes(file.size)} · 修改于 ${new Date(file.lastModified).toLocaleString('zh-CN', { hour12: false })}`;
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
}

async function loadHdfsFiles(path = hdfsPath) {
    try {
        const data = await fetchJson(`/api/hdfs/files/?path=${encodeURIComponent(path)}`);
        hdfsPath = data.path;
        hdfsParentPath = data.parent;
        $('hdfsCurrentPath').textContent = data.path;
        $('hdfsParentButton').disabled = !data.parent;
        $('hdfsFilesBody').innerHTML = data.items.map(item => {
            const modified = new Date(item.modification_time).toLocaleString('zh-CN', { hour12: false });
            const isDirectory = item.type === 'directory';
            return `<tr>
                <td><button class="file-name-button ${isDirectory ? 'directory' : ''}" data-open="${escapeHtml(item.path)}" data-type="${item.type}">${isDirectory ? '▣' : '▤'} ${escapeHtml(item.name)}</button></td>
                <td>${isDirectory ? '目录' : '文件'}</td>
                <td>${isDirectory ? '--' : formatBytes(item.length)}</td>
                <td>${modified}</td>
                <td>
                    ${isDirectory ? '' : `<button class="file-action" data-preview="${escapeHtml(item.path)}">查看</button>`}
                    <button class="file-action delete" data-delete="${escapeHtml(item.path)}" data-recursive="${isDirectory}">删除</button>
                </td>
            </tr>`;
        }).join('') || '<tr><td colspan="5" class="empty-state">目录为空</td></tr>';
    } catch (error) {
        $('hdfsFilesBody').innerHTML = `<tr><td colspan="5">${escapeHtml(error.message)}</td></tr>`;
        showToast(error.message);
    }
}

async function previewHdfsFile(path) {
    try {
        $('previewPanel').open = true;
        $('previewTitle').textContent = path;
        $('filePreviewContent').textContent = '正在读取...';
        const data = await fetchJson(`/api/hdfs/preview/?path=${encodeURIComponent(path)}`);
        $('filePreviewContent').textContent = data.content;
    } catch (error) {
        $('filePreviewContent').textContent = error.message;
        showToast(error.message);
    }
}

async function deleteHdfsItem(path, recursive) {
    if (!window.confirm(`确定删除 ${path} 吗？`)) return;
    try {
        const data = await fetchJson('/api/hdfs/delete/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, recursive })
        });
        showToast(data.message);
        await loadHdfsFiles();
    } catch (error) {
        showToast(error.message);
    }
}

function setJobStatus(job) {
    const statusText = {
        queued: '任务排队中',
        running: 'MapReduce 计算中',
        success: '计算与同步完成',
        failed: '任务执行失败'
    };
    $('jobStatusText').textContent = job ? (statusText[job.status] || job.message) : '暂无运行任务';
    $('jobStatusTime').textContent = job?.finished_at || job?.started_at || job?.created_at || '--';
    $('jobStatusDot').className = `status-dot job-${job?.status || 'idle'}`;
    $('jobProgress').className = job?.status || '';
    $('jobLog').textContent = job?.output_log || job?.message || '等待任务...';
    const busy = job && ['queued', 'running'].includes(job.status);
    $('runJobButton').disabled = busy;
    $('uploadButton').disabled = busy;
}

async function pollJobStatus(jobId = activeJobId) {
    if (jobPollTimer) clearTimeout(jobPollTimer);
    try {
        const data = await fetchJson(`/api/hdfs/jobs/status/${jobId ? `?id=${jobId}` : ''}`);
        const job = data.job;
        setJobStatus(job);
        if (!job) return;
        activeJobId = job.id;
        if (['queued', 'running'].includes(job.status)) {
            jobPollTimer = setTimeout(() => pollJobStatus(job.id), 3000);
        } else {
            activeJobId = null;
            await loadHdfsFiles();
            if (job.status === 'success') {
                showToast(job.message);
                if (job.auto_refresh && $('trendChart')) await loadDashboard(false, false);
            } else if (job.status === 'failed') {
                showToast(job.message);
            }
        }
    } catch (error) {
        setJobStatus(null);
        showToast(error.message);
    }
}

async function startMapReduceJob() {
    try {
        const data = await fetchJson('/api/hdfs/jobs/start/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_refresh: $('autoRefreshCharts').checked })
        });
        activeJobId = data.job.id;
        setJobStatus(data.job);
        showToast('MapReduce 任务已启动');
        pollJobStatus(activeJobId);
    } catch (error) {
        showToast(error.message);
        pollJobStatus();
    }
}

async function uploadHdfsFile(event) {
    event.preventDefault();
    const file = $('hdfsFile').files[0];
    if (!file) {
        showToast('请先选择文件');
        return;
    }
    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', '/waether/input');
    formData.append('clear_input', String($('clearInput').checked));
    formData.append('overwrite', String($('overwriteFile').checked));
    formData.append('auto_run', String($('autoRunJob').checked));
    formData.append('auto_refresh', String($('autoRefreshCharts').checked));
    $('uploadButton').disabled = true;
    $('jobProgress').className = 'running';
    $('jobLog').textContent = `正在上传 ${file.name}...`;
    try {
        const data = await fetchJson('/api/hdfs/upload/', { method: 'POST', body: formData });
        showToast(data.message);
        $('hdfsUploadForm').reset();
        $('clearInput').checked = true;
        $('overwriteFile').checked = true;
        $('autoRunJob').checked = true;
        $('autoRefreshCharts').checked = true;
        showSelectedFile(null);
        await loadHdfsFiles('/waether/input');
        if (data.job) {
            activeJobId = data.job.id;
            setJobStatus(data.job);
            pollJobStatus(activeJobId);
        } else {
            $('jobProgress').className = 'success';
            $('jobLog').textContent = data.message;
            $('uploadButton').disabled = false;
        }
    } catch (error) {
        $('jobProgress').className = 'failed';
        $('jobLog').textContent = error.message;
        $('uploadButton').disabled = false;
        showToast(error.message);
    }
}

async function syncDatabaseAndRefresh() {
    $('syncResultsButton').disabled = true;
    try {
        const data = await fetchJson('/api/hdfs/sync/', { method: 'POST' });
        showToast(data.message);
        if ($('trendChart')) await loadDashboard(false, false);
    } catch (error) {
        showToast(error.message);
    } finally {
        $('syncResultsButton').disabled = false;
    }
}

function showToast(message) {
    const toast = $('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

function bindDashboardEvents() {
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

function bindHdfsEvents() {
    $('hdfsUploadForm').addEventListener('submit', uploadHdfsFile);
    $('hdfsFile').addEventListener('change', () => showSelectedFile($('hdfsFile').files[0]));
    const dropZone = $('fileDropZone');
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, event => {
            event.preventDefault();
            dropZone.classList.add('dragging');
        });
    });
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, event => {
            event.preventDefault();
            dropZone.classList.remove('dragging');
        });
    });
    dropZone.addEventListener('drop', event => {
        const file = event.dataTransfer.files[0];
        if (!file) return;
        const extension = file.name.toLowerCase().split('.').pop();
        if (!['csv', 'txt'].includes(extension)) {
            showToast('请选择 CSV 或 TXT 文件');
            return;
        }
        const transfer = new DataTransfer();
        transfer.items.add(file);
        $('hdfsFile').files = transfer.files;
        showSelectedFile(file);
    });
    $('runJobButton').addEventListener('click', startMapReduceJob);
    $('syncResultsButton').addEventListener('click', syncDatabaseAndRefresh);
    $('refreshHdfsButton').addEventListener('click', () => loadHdfsFiles());
    $('hdfsParentButton').addEventListener('click', () => {
        if (hdfsParentPath) loadHdfsFiles(hdfsParentPath);
    });
    $('hdfsFilesBody').addEventListener('click', event => {
        const openButton = event.target.closest('[data-open]');
        const previewButton = event.target.closest('[data-preview]');
        const deleteButton = event.target.closest('[data-delete]');
        if (openButton) {
            if (openButton.dataset.type === 'directory') loadHdfsFiles(openButton.dataset.open);
            else previewHdfsFile(openButton.dataset.open);
        } else if (previewButton) {
            previewHdfsFile(previewButton.dataset.preview);
        } else if (deleteButton) {
            deleteHdfsItem(deleteButton.dataset.delete, deleteButton.dataset.recursive === 'true');
        }
    });
    $('closePreviewButton').addEventListener('click', () => {
        $('previewTitle').textContent = '文件预览';
        $('filePreviewContent').textContent = '点击文件的“查看”按钮可预览前 64 KB 内容。';
        $('previewPanel').open = false;
    });
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
    if ($('trendChart')) {
        bindDashboardEvents();
        loadDashboard();
    }
    if ($('hdfsUploadForm')) {
        bindHdfsEvents();
        loadHdfsFiles();
        pollJobStatus();
    }
});
