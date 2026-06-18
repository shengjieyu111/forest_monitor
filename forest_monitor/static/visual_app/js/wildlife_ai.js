const wildlife = {
    imageFile: null
};

function setWildlifeFile(file) {
    wildlife.imageFile = file;
    resetWildlifeResult();
    if (!file) {
        $('wildlifeFileName').textContent = '支持 JPG / PNG / WEBP，建议小于 8 MB';
        $('wildlifeFileMeta').textContent = '图片会在本地页面预览，并提交到 Django 后端推理';
        $('wildlifePreviewImage').removeAttribute('src');
        $('wildlifePreviewImage').classList.remove('show');
        $('wildlifeEmpty').style.display = 'grid';
        return;
    }
    $('wildlifeFileName').textContent = file.name;
    $('wildlifeFileMeta').textContent = `${formatBytes(file.size)} · ${file.type || 'image'}`;
    const reader = new FileReader();
    reader.onload = () => {
        $('wildlifePreviewImage').src = reader.result;
        $('wildlifePreviewImage').classList.add('show');
        $('wildlifeEmpty').style.display = 'none';
    };
    reader.readAsDataURL(file);
}

function resetWildlifeResult() {
    if (!$('summaryTitle')) return;
    $('wildlifeState').textContent = '等待识别';
    $('summaryTitle').textContent = '待识别';
    $('summarySubtitle').textContent = '已更换图片，请点击开始 AI 识别';
    $('summaryConfidence').textContent = '--';
    $('summaryEvidence').textContent = '新图片尚未完成推理，结果区会在后端返回后自动刷新。';
    $('modelStatusList').innerHTML = '<div class="empty-state">等待模型推理</div>';
    $('recommendationList').innerHTML = '<li>识别完成后生成适合游客阅读的自然观察与科普提示。</li>';
    $('detectionBody').innerHTML = '<tr><td colspan="4">暂无检测结果</td></tr>';
    $('visitorProfile').innerHTML = '<div class="empty-state">识别完成后展示物种名片</div>';
    $('touristGuide').innerHTML = defaultTouristTips();
    $('natureClassroom').innerHTML = '<p>鹫峰国家森林公园位于北京西山生态廊道，森林、灌丛、草地和沟谷湿地共同构成多样生境。识别结果可作为自然观察参考，遇到不确定物种时建议拍照记录并咨询专业人员。</p>';
}

function bindWildlifeEvents() {
    const dropZone = $('wildlifeDropZone');
    $('wildlifeImage').addEventListener('change', () => setWildlifeFile($('wildlifeImage').files[0]));
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
        if (!file.type.startsWith('image/')) {
            showToast('请选择图片文件');
            return;
        }
        const transfer = new DataTransfer();
        transfer.items.add(file);
        $('wildlifeImage').files = transfer.files;
        setWildlifeFile(file);
    });
    document.querySelectorAll('.model-choice input').forEach(input => {
        input.addEventListener('change', () => {
            document.querySelectorAll('.model-choice').forEach(label => label.classList.toggle('active', label.contains(input) && input.checked));
        });
    });
    $('wildlifeForm').addEventListener('submit', submitWildlifeAnalysis);
}

async function submitWildlifeAnalysis(event) {
    event.preventDefault();
    const file = $('wildlifeImage').files[0];
    if (!file) {
        showToast('请先上传野生动物图片');
        return;
    }
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const formData = new FormData();
    formData.append('image', file);
    formData.append('mode', mode);
    formData.append('category', $('wildlifeCategory')?.value || 'auto');
    $('wildlifeSubmit').disabled = true;
    $('wildlifeState').textContent = '推理中...';
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);
    try {
        const data = await fetchJson(`/api/ai/wildlife/analyze/?t=${Date.now()}`, {
            method: 'POST',
            body: formData,
            signal: controller.signal
        });
        renderWildlifeResult(data);
        showToast('AI 识别完成');
    } catch (error) {
        $('wildlifeState').textContent = '识别失败';
        showToast(error.name === 'AbortError' ? '推理超时，请确认模型文件或重启服务' : error.message);
    } finally {
        clearTimeout(timeoutId);
        $('wildlifeSubmit').disabled = false;
    }
}

function renderWildlifeResult(data) {
    $('wildlifeState').textContent = data.summary.risk;
    $('wildlifePreviewImage').src = data.image.annotated;
    $('wildlifePreviewImage').classList.add('show');
    $('wildlifeEmpty').style.display = 'none';
    $('summaryTitle').textContent = data.summary.title;
    $('summarySubtitle').textContent = data.summary.subtitle;
    $('summaryConfidence').textContent = `${Math.round(data.summary.confidence * 100)}%`;
    $('summaryEvidence').textContent = data.summary.evidence;
    renderModelStatus(data.models);
    renderDetections(data.detections);
    renderVisitorSections(data);
    $('recommendationList').innerHTML = data.recommendations.map(item => `<li>${escapeHtml(item)}</li>`).join('');
}

function renderModelStatus(models) {
    const statusClass = {
        ready: 'ready',
        fallback: 'fallback',
        skipped: 'skipped'
    };
    $('modelStatusList').innerHTML = Object.values(models).map(model => `
        <div class="model-status-item ${statusClass[model.status] || ''}">
            <span class="status-dot"></span>
            <div>
                <strong>${escapeHtml(model.name || model.type)}</strong>
                <small>${escapeHtml(model.type || '')} · ${escapeHtml(model.message || '')}</small>
            </div>
        </div>
    `).join('');
}

function renderDetections(detections) {
    $('detectionBody').innerHTML = detections.map(item => `
        <tr>
            <td>${escapeHtml(item.label)}</td>
            <td>${Math.round(item.confidence * 100)}%</td>
            <td>${item.box.join(', ')}</td>
            <td>${escapeHtml(item.model)}</td>
        </tr>
    `).join('') || '<tr><td colspan="4">未检测到明确动物目标</td></tr>';
}

function renderVisitorSections(data) {
    const top = data.classifications?.[0] || null;
    if (!top) {
        $('visitorProfile').innerHTML = '<div class="empty-state">未识别到明确物种，可重新上传更清晰图片</div>';
        $('touristGuide').innerHTML = defaultTouristTips();
        return;
    }
    $('visitorProfile').innerHTML = `
        <div class="profile-title">
            <span>${escapeHtml(top.group || '自然物种')}</span>
            <strong>${escapeHtml(top.label)}</strong>
            <small>${escapeHtml(top.english)} · 可信度 ${Math.round(top.confidence * 100)}%</small>
        </div>
        <div class="profile-facts">
            <div><b>保护/生态属性</b><span>${escapeHtml(top.level)}</span></div>
            <div><b>常见生境</b><span>${escapeHtml(top.habitat)}</span></div>
            <div><b>观察重点</b><span>${escapeHtml(getObservationFocus(top))}</span></div>
        </div>
    `;
    $('touristGuide').innerHTML = buildTouristTips(top);
    $('natureClassroom').innerHTML = `
        <p>${escapeHtml(buildNatureText(top))}</p>
    `;
}

function getObservationFocus(item) {
    const group = item.group || '';
    if (group === '鸟类') return '观察羽色、鸣叫、停栖位置和飞行方式。';
    if (group === '爬行动物') return '观察体形、行动方式和所在微生境，保持安全距离。';
    if (group === '植物') return '观察叶形、树皮、花果和生长环境，不采摘。';
    return '观察体型、毛色、足迹、活动时间和与人的距离。';
}

function buildTouristTips(item) {
    const group = item.group || '';
    const common = [
        ['拍照记录', '拍下整体、局部特征和周边环境，便于后续复核。'],
        ['不打扰', '不要投喂、追赶、采摘或移动它，让自然保持原样。']
    ];
    const groupTips = {
        '鸟类': [['安静观鸟', '放低音量，避免靠近巢区和幼鸟。'], ['使用望远镜', '远距离观察比靠近拍摄更安全。']],
        '爬行动物': [['保持距离', '蛇类和蜥蜴受惊会逃逸或防御，不要伸手触碰。'], ['留意脚下', '走步道，避免翻石块和踩踏草丛。']],
        '植物': [['只看不采', '花、果、叶都是生态链的一部分。'], ['看生境', '记录阳坡、阴坡、林下或沟谷等环境差异。']],
        '兽类': [['慢慢后退', '偶遇兽类不要围堵，给它留出离开的通道。'], ['不投喂', '投喂会改变野生动物行为并增加冲突风险。']]
    };
    return [...(groupTips[group] || []), ...common].map(([title, text]) => `
        <div class="tourist-tip"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(text)}</span></div>
    `).join('');
}

function buildNatureText(item) {
    const group = item.group || '自然物种';
    if (group === '植物') {
        return `${item.label}所在的植物群落为鸟类、昆虫和小型动物提供食物与隐蔽空间。游客观察植物时，可以把叶形、花果、树皮和生境一起记录下来，这比单独拍一片叶子更有科普价值。`;
    }
    if (group === '鸟类') {
        return `${item.label}是森林生态中重要的活动成员。鸟类常通过取食昆虫、传播种子或占据不同林层来维持生态平衡，观鸟时安静和距离感就是最好的保护。`;
    }
    if (group === '爬行动物') {
        return `${item.label}对温度和微生境非常敏感，是观察林地生态健康的好线索。遇到爬行动物时保持距离即可，它们通常会主动避开人类。`;
    }
    return `${item.label}的出现说明周边生境为野生动物提供了食物、水源或隐蔽条件。游客可以记录时间、地点和行为，但不要改变动物的自然活动路线。`;
}

function defaultTouristTips() {
    return `
        <div class="tourist-tip"><strong>保持距离</strong><span>不追逐、不投喂、不触摸野生动植物。</span></div>
        <div class="tourist-tip"><strong>轻声观察</strong><span>降低噪声，给动物留下安全活动空间。</span></div>
        <div class="tourist-tip"><strong>只拍不采</strong><span>植物和昆虫都属于生态系统的一部分。</span></div>
    `;
}

document.addEventListener('DOMContentLoaded', () => {
    if ($('wildlifeForm')) bindWildlifeEvents();
});
