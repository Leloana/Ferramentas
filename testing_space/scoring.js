// Scoring module for snooker game

// Pocket coordinates (x, y) for 6 pockets on 800x400 canvas
const POCKETS = [
    { x: 0, y: 0 },                    // Top-left
    { x: 800, y: 0 },                  // Top-right
    { x: 400, y: 0 },                  // Top-middle
    { x: 0, y: 400 },                  // Bottom-left
    { x: 800, y: 400 },                // Bottom-right
    { x: 400, y: 400 }                 // Bottom-middle
];

// Ball color point values
const BALL_POINTS = {
    red: 1,
    yellow: 2,
    green: 3,
    brown: 4,
    blue: 5,
    pink: 6,
    black: 7
};

// Pocket radius for detection
const POCKET_RADIUS = 30;

/**
 * Check if a ball is within any pocket and return point value
 * @param {Object} ball - Ball object with x, y, and color properties
 * @returns {number|null} Point value if potted, null otherwise
 */
function checkPot(ball) {
    if (!ball || !ball.x || !ball.y) {
        return null;
    }

    // Check each pocket
    for (const pocket of POCKETS) {
        const dx = ball.x - pocket.x;
        const dy = ball.y - pocket.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        // If ball is within pocket radius, return point value
        if (distance <= POCKET_RADIUS) {
            return BALL_POINTS[ball.color] || null;
        }
    }

    return null;
}

// Export for use in game
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { checkPot, POCKETS, BALL_POINTS };
}
