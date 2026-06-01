// Snooker Game Main Logic
const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');
const scoreDisplay = document.getElementById('score');

// Ball configuration
const balls = [];
const pockets = [];
const cueBall = null;

// Initialize balls
function initBalls() {
    // Create 15 colored balls in triangle formation
    const ballRadius = 10;
    const startX = 100;
    const startY = 200;
    const spacing = 25;
    
    const colors = ['yellow', 'green', 'brown', 'blue', 'pink', 'black'];
    const ballValues = { 'yellow': 1, 'green': 2, 'brown': 3, 'blue': 4, 'pink': 5, 'black': 6 };
    
    // Cue ball
    cueBall = { x: 700, y: 200, radius: ballRadius, color: 'white', value: 0, velocity: { x: 0, y: 0 } };
    balls.push(cueBall);
    
    // Triangle formation for colored balls
    let row = 0;
    let col = 0;
    for (let i = 0; i < 5; i++) {
        for (let j = 0; j <= i; j++) {
            const x = startX + j * spacing;
            const y = startY - (i * spacing) + (i * ballRadius);
            const color = colors[i];
            const ball = { x, y, radius: ballRadius, color, value: ballValues[color], velocity: { x: 0, y: 0 } };
            balls.push(ball);
        }
    }
}

// Initialize pockets
function initPockets() {
    const pocketRadius = 15;
    pockets.push({ x: 0, y: 0, radius: pocketRadius });
    pockets.push({ x: 0, y: 400, radius: pocketRadius });
    pockets.push({ x: 400, y: 0, radius: pocketRadius });
    pockets.push({ x: 400, y: 400, radius: pocketRadius });
    pockets.push({ x: 800, y: 0, radius: pocketRadius });
    pockets.push({ x: 800, y: 400, radius: pocketRadius });
}

// Check if ball is in pocket
function checkPot(ball) {
    for (const pocket of pockets) {
        const dx = ball.x - pocket.x;
        const dy = ball.y - pocket.y;
        if (Math.sqrt(dx * dx + dy * dy) < pocket.radius) {
            return checkPotFunction(ball);
        }
    }
    return null;
}

// Check pot function from scoring.js
function checkPotFunction(ball) {
    // This would be imported from scoring.js
    return ball.value;
}

// Update ball positions
function update() {
    for (const ball of balls) {
        ball.x += ball.velocity.x;
        ball.y += ball.velocity.y;
        
        // Friction
        ball.velocity.x *= 0.99;
        ball.velocity.y *= 0.99;
        
        // Wall collision
        if (ball.x < ball.radius || ball.x > canvas.width - ball.radius) {
            ball.velocity.x *= -1;
        }
        if (ball.y < ball.radius || ball.y > canvas.height - ball.radius) {
            ball.velocity.y *= -1;
        }
    }
}

// Draw the game
function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw pockets
    ctx.fillStyle = '#333';
    for (const pocket of pockets) {
        ctx.beginPath();
        ctx.arc(pocket.x, pocket.y, pocket.radius, 0, Math.PI * 2);
        ctx.fill();
    }
    
    // Draw balls
    for (const ball of balls) {
        ctx.beginPath();
        ctx.arc(ball.x, ball.y, ball.radius, 0, Math.PI * 2);
        ctx.fillStyle = ball.color;
        ctx.fill();
        ctx.strokeStyle = '#000';
        ctx.stroke();
    }
    
    // Draw cue stick
    drawCue();
    
    // Draw score
    scoreDisplay.textContent = `Score: ${calculateScore()}`;
}

// Draw cue stick
function drawCue() {
    const cueX = cueBall.x - 30;
    const cueY = cueBall.y;
    ctx.fillStyle = '#8B4513';
    ctx.fillRect(cueX, cueY - 5, 30, 10);
}

// Calculate total score
function calculateScore() {
    let score = 0;
    for (const ball of balls) {
        if (ball !== cueBall) {
            score += ball.value;
        }
    }
    return score;
}

// Handle click to shoot
function shoot() {
    if (cueBall.velocity.x === 0 && cueBall.velocity.y === 0) {
        const angle = Math.atan2(mouseY - cueBall.y, mouseX - cueBall.x);
        const power = 8;
        cueBall.velocity.x = Math.cos(angle) * power;
        cueBall.velocity.y = Math.sin(angle) * power;
    }
}

// Event listeners
canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    mouseY = e.clientY - rect.top;
    shoot();
});

// Initialize game
initBalls();
initPockets();

// Game loop
function gameLoop() {
    update();
    draw();
    requestAnimationFrame(gameLoop);
}

gameLoop();
