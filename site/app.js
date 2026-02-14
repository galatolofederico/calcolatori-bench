document.addEventListener('DOMContentLoaded', async () => {
    try {
        const res = await fetch('leaderboard_data.json');
        const data = await res.json();
        renderLeaderboard(data);
        renderDetailed(data);
        renderStats(data);
    } catch (e) {
        document.getElementById('leaderboard-body').innerHTML = 
            '<tr><td colspan="4">No results yet</td></tr>';
    }
});

function renderLeaderboard(data) {
    const tbody = document.getElementById('leaderboard-body');
    
    if (!data.models?.length) {
        tbody.innerHTML = '<tr><td colspan="4">No results yet</td></tr>';
        return;
    }

    tbody.innerHTML = data.models.map((model, i) => {
        const s = data.model_stats[model];
        return `
            <tr>
                <td class="rank">${i + 1}</td>
                <td class="model">${esc(model)}</td>
                <td class="score">${s.passed}/${s.total}</td>
                <td class="bar-cell"><div class="bar"><div class="bar-fill" style="width:${s.percentage}%"></div></div></td>
            </tr>
        `;
    }).join('');
}

function renderDetailed(data) {
    const thead = document.getElementById('results-head');
    const tbody = document.getElementById('results-body');

    if (!data.models?.length || !data.exams?.length) return;

    thead.innerHTML = `<tr><th class="model-col">Model</th>${data.exams.map(e => `<th>${esc(e)}</th>`).join('')}<th>Total</th></tr>`;

    tbody.innerHTML = data.models.map(model => {
        let passed = 0;
        const cells = data.exams.map(exam => {
            const r = data.exam_results[exam]?.[model];
            if (r?.passed === true) { passed++; return '<td class="pass">&#10003;</td>'; }
            if (r?.passed === false) return '<td class="fail">&#10007;</td>';
            return '<td class="na">-</td>';
        }).join('');
        return `<tr><td class="model-col">${esc(model)}</td>${cells}<td class="pass">${passed}/${data.exams.length}</td></tr>`;
    }).join('');
}

function renderStats(data) {
    document.getElementById('total-models').textContent = data.total_models || 0;
    document.getElementById('total-exams').textContent = data.total_exams || 0;
    if (data.generated_at) {
        document.getElementById('last-updated').textContent = 
            new Date(data.generated_at).toLocaleDateString();
    }
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
