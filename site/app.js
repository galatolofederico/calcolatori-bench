document.addEventListener('DOMContentLoaded', async () => {
    try {
        const res = await fetch('leaderboard_data.json');
        const data = await res.json();
        renderLeaderboard(data);
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
            <tr onclick="window.location.href='detail.html?model=${encodeURIComponent(model)}'" class="clickable">
                <td class="rank">${i + 1}</td>
                <td class="model">${esc(model)}</td>
                <td class="score">${s.passed}/${s.total}</td>
                <td class="bar-cell"><div class="bar"><div class="bar-fill" style="width:${s.percentage}%"></div></div></td>
            </tr>
        `;
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
