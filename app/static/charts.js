/**
 * Chart.js helper utilities for Team Maturity Assessment dashboards.
 * Individual chart configs are embedded in the templates for simplicity.
 * This file holds shared defaults and utility functions.
 */

// Set global Chart.js defaults
if (typeof Chart !== 'undefined') {
    Chart.defaults.font.family = "'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#000000';
    Chart.defaults.borderColor = 'rgba(0, 0, 0, 0.15)';
    Chart.defaults.plugins.tooltip.cornerRadius = 0;
    Chart.defaults.plugins.tooltip.padding = 10;
}

/**
 * Color palette for consistent chart styling.
 */
const MATURITY_COLORS = {
    categories: [
        'rgba(76, 182, 72, 0.7)',    // DFW green - Responsiveness
        'rgba(59, 130, 246, 0.7)',   // DFW blue - Continuous Improvement
        'rgba(234, 179, 8, 0.7)',    // yellow - Stakeholders
        'rgba(239, 68, 68, 0.7)',    // red - Team Effectiveness
        'rgba(99, 102, 241, 0.7)',   // indigo - Team Autonomy
        'rgba(236, 72, 153, 0.7)',   // pink - Management Support
    ],
    categoryBorders: [
        'rgb(76, 182, 72)',
        'rgb(59, 130, 246)',
        'rgb(234, 179, 8)',
        'rgb(239, 68, 68)',
        'rgb(99, 102, 241)',
        'rgb(236, 72, 153)',
    ],
};

/**
 * Get a color-coded class suffix based on a 1-5 score.
 */
function scoreColorClass(score) {
    if (score >= 4.0) return 'green';
    if (score >= 3.0) return 'yellow';
    if (score >= 2.0) return 'orange';
    return 'red';
}
