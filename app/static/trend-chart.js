/**
 * Highlight-on-hover trend chart.
 * Lines show real colors by default. Hovering a legend item highlights that line,
 * fading all others to gray. Clicking a legend item toggles sticky highlight.
 * Mouse leave restores all colors.
 */
function createHighlightTrendChart(canvasId, labels, datasets, opts = {}) {
    const colors = ['#6366f1', '#22c55e', '#3b82f6', '#f97316', '#ef4444', '#a855f7', '#14b8a6', '#64748b'];
    const GRAY = '#e2e8f0';
    const GRAY_POINT = '#cbd5e1';
    const yMax = opts.yMax || 5;
    const yLabel = opts.yLabel || 'Score';
    const yTickCallback = opts.yTickCallback || null;

    let activeIndex = -1;
    let sticky = false;

    const chartDatasets = datasets.map((ds, i) => ({
        label: ds.label,
        data: ds.data,
        borderColor: colors[i % colors.length],
        backgroundColor: 'transparent',
        pointBackgroundColor: colors[i % colors.length],
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        tension: 0.3,
        fill: false,
        borderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 6,
        _color: colors[i % colors.length],
        spanGaps: true,
    }));

    const canvas = document.getElementById(canvasId);
    const chart = new Chart(canvas, {
        type: 'line',
        data: { labels, datasets: chartDatasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'dataset', intersect: false },
            scales: {
                y: {
                    beginAtZero: true,
                    max: yMax,
                    title: { display: true, text: yLabel },
                    grid: { color: 'rgba(0, 0, 0, 0.06)' },
                    ...(yTickCallback ? { ticks: { stepSize: 1, callback: yTickCallback } } : {}),
                },
                x: {
                    grid: { color: 'rgba(0, 0, 0, 0.04)' },
                },
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        usePointStyle: false,
                        boxWidth: 14,
                        boxHeight: 14,
                        generateLabels(chart) {
                            return chart.data.datasets.map((ds, i) => ({
                                text: ds.label,
                                fillStyle: activeIndex === -1 || activeIndex === i ? ds._color : GRAY,
                                strokeStyle: activeIndex === -1 || activeIndex === i ? ds._color : GRAY,
                                lineWidth: 0,
                                datasetIndex: i,
                                hidden: !chart.isDatasetVisible(i),
                            }));
                        },
                    },
                    onHover(e, legendItem) {
                        if (sticky) return;
                        if (legendItem) highlight(legendItem.datasetIndex);
                    },
                    onLeave() {
                        if (sticky) return;
                        resetHighlight();
                    },
                    onClick(e, legendItem) {
                        if (!legendItem) return;
                        const idx = legendItem.datasetIndex;
                        if (sticky && activeIndex === idx) {
                            sticky = false;
                            resetHighlight();
                        } else {
                            sticky = true;
                            highlight(idx);
                        }
                    },
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const val = ctx.parsed.y;
                            if (val == null) return ctx.dataset.label + ': —';
                            let txt = ctx.dataset.label + ': ' + val.toFixed(1);
                            if (yTickCallback) {
                                const lvl = yTickCallback(Math.round(val));
                                if (lvl) txt += ' (' + lvl + ')';
                            }
                            return txt;
                        },
                    },
                },
            },
        },
    });

    function highlight(idx) {
        if (activeIndex === idx) return;
        activeIndex = idx;
        chart.data.datasets.forEach((ds, i) => {
            if (i === idx) {
                ds.borderColor = ds._color;
                ds.borderWidth = 3;
                ds.pointBackgroundColor = ds._color;
                ds.pointBorderColor = '#fff';
                ds.pointRadius = 6;
                ds.pointBorderWidth = 2;
            } else {
                ds.borderColor = GRAY;
                ds.borderWidth = 1;
                ds.pointBackgroundColor = GRAY_POINT;
                ds.pointBorderColor = GRAY_POINT;
                ds.pointRadius = 3;
                ds.pointBorderWidth = 0;
            }
        });
        chart.update('none');
    }

    function resetHighlight() {
        if (activeIndex === -1) return;
        activeIndex = -1;
        chart.data.datasets.forEach((ds) => {
            ds.borderColor = ds._color;
            ds.borderWidth = 2;
            ds.pointBackgroundColor = ds._color;
            ds.pointBorderColor = '#fff';
            ds.pointBorderWidth = 2;
            ds.pointRadius = 4;
        });
        chart.update('none');
    }

    canvas.addEventListener('mouseleave', () => {
        if (!sticky) resetHighlight();
    });

    return chart;
}
