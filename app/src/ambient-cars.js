/**
 * SGIP - Dynamic Ambient Vehicles Controller
 * Simulates living campus parking traffic with randomized routes, natural steering,
 * multi-palette vehicles, and real-time collision avoidance.
 */

const ROUTES_DATA = [
  // 1. Acceso Norte -> Avenida Central (Carril Sur) -> Salida Sur
  [
    [71.0, 16.0], [72.5, 45.0], [74.0, 72.0], [78.0, 98.0],
    [86.0, 126.0], [96.0, 148.0], [107.0, 168.0], [108.5, 178.0]
  ],
  // 2. Acceso Sur -> Avenida Central (Carril Norte) -> Salida Norte
  [
    [111.0, 176.0], [110.0, 166.0], [100.5, 144.0], [91.0, 120.0],
    [83.0, 90.0], [76.5, 56.0], [75.0, 20.0], [74.5, 14.0]
  ],
  // 3. Acceso Noroeste -> Incorporación Central -> Salida Sur
  [
    [35.0, 48.0], [52.0, 32.0], [68.0, 34.0], [74.0, 60.0],
    [78.0, 98.0], [86.0, 126.0], [96.0, 148.0], [107.0, 168.0], [108.5, 178.0]
  ],
  // 4. Acceso Norte -> Giro hacia pasillo L1-L2 (Sentido Único Oeste) -> Salida Oeste
  [
    [71.0, 16.0], [73.0, 55.0], [70.0, 84.0], [52.0, 95.0],
    [32.0, 107.0], [14.0, 118.0]
  ],
  // 5. Acceso Noroeste -> Incorporación Central -> Salida Norte
  [
    [35.0, 48.0], [52.0, 32.0], [68.0, 34.0], [76.0, 34.0],
    [76.5, 20.0], [75.0, 14.0]
  ],
  // 6. Acceso Delantal Sur -> Avenida Central -> Salida Norte
  [
    [52.0, 175.0], [70.0, 172.0], [90.0, 170.0], [110.0, 166.0],
    [100.5, 144.0], [91.0, 120.0], [83.0, 90.0], [76.5, 56.0], [75.0, 20.0], [74.5, 14.0]
  ]
];

const CAR_PALETTES = [
  { body: '#f8fafc', stroke: '#cbd5e1', roof: '#e2e8f0', glass: '#334155' }, // Blanco Perla
  { body: '#1e3a8a', stroke: '#1d4ed8', roof: '#2563eb', glass: '#0f172a' }, // Azul Marino
  { body: '#475569', stroke: '#334155', roof: '#64748b', glass: '#0f172a' }, // Gris Pizarra
  { body: '#991b1b', stroke: '#b91c1c', roof: '#dc2626', glass: '#1e1b4b' }, // Rojo Carmesí
  { body: '#d97706', stroke: '#b45309', roof: '#f59e0b', glass: '#1c1917' }, // Dorado Ámbar
  { body: '#15803d', stroke: '#16a34a', roof: '#22c55e', glass: '#064e3b' }, // Verde Esmeralda
];

function prepareRoute(pts) {
  const segs = [];
  let total = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const len = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
    const ang = Math.atan2(p2[1] - p1[1], p2[0] - p1[0]) * (180 / Math.PI);
    segs.push({ p1, p2, len, ang, startDist: total });
    total += len;
  }
  return { pts, segs, total };
}

const PREPARED_ROUTES = ROUTES_DATA.map(prepareRoute);

function normalizeDeg(deg) {
  while (deg > 180) deg -= 360;
  while (deg < -180) deg += 360;
  return deg;
}

export class AmbientCarManager {
  constructor(containerElement, carCount = 3) {
    this.container = containerElement;
    this.carCount = carCount;
    this.cars = [];
    this.animId = null;
    this.lastTimestamp = null;
    this.boundTick = this.tick.bind(this);
    this.boundVisibility = this.handleVisibilityChange.bind(this);
  }

  init() {
    if (!this.container) return;
    this.container.innerHTML = '';

    for (let i = 0; i < this.carCount; i++) {
      const car = this.createCar(i);
      this.cars.push(car);
      this.container.appendChild(car.element);
      // Stagger start times
      car.waitTimer = i * 4.5 + Math.random() * 2.0;
    }

    document.addEventListener('visibilitychange', this.boundVisibility);
    this.animId = requestAnimationFrame(this.boundTick);
  }

  createCar(id) {
    const palette = CAR_PALETTES[id % CAR_PALETTES.length];
    const element = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    element.setAttribute('class', 'ambient-car');
    element.style.opacity = '0';
    element.innerHTML = `
      <rect class="car-shadow" x="-2.7" y="-1.5" width="5.4" height="3.0" rx="1.0" fill="rgba(15, 23, 42, 0.22)" filter="blur(0.35px)" />
      <rect class="car-body" x="-2.6" y="-1.35" width="5.2" height="2.7" rx="0.8" fill="${palette.body}" stroke="${palette.stroke}" stroke-width="0.25" />
      <rect class="car-windshield" x="0.4" y="-1.05" width="0.85" height="2.1" rx="0.25" fill="${palette.glass}" />
      <rect class="car-rear" x="-2.1" y="-1.0" width="0.6" height="2.0" rx="0.2" fill="${palette.glass}" />
      <rect class="car-roof" x="-1.35" y="-1.1" width="1.7" height="2.2" rx="0.4" fill="${palette.roof}" />
      <circle class="car-headlight" cx="2.35" cy="-0.85" r="0.28" fill="#fef08a" />
      <circle class="car-headlight" cx="2.35" cy="0.85" r="0.28" fill="#fef08a" />
      <circle class="car-taillight" cx="-2.45" cy="-0.85" r="0.26" fill="#ef4444" />
      <circle class="car-taillight" cx="-2.45" cy="0.85" r="0.26" fill="#ef4444" />
    `;

    return {
      id,
      element,
      routeIdx: null,
      dist: 0,
      baseSpeed: 8.0 + Math.random() * 2.2, // 8.0 - 10.2 SVG units/sec
      currentSpeed: 0,
      x: 0,
      y: 0,
      heading: 0,
      opacity: 0,
      state: 'waiting', // 'waiting' | 'driving'
      waitTimer: 0,
      blockedTime: 0,
    };
  }

  updateCarPalette(car) {
    const palette = CAR_PALETTES[Math.floor(Math.random() * CAR_PALETTES.length)];
    const body = car.element.querySelector('.car-body');
    const roof = car.element.querySelector('.car-roof');
    const glass1 = car.element.querySelector('.car-windshield');
    const glass2 = car.element.querySelector('.car-rear');

    if (body) {
      body.setAttribute('fill', palette.body);
      body.setAttribute('stroke', palette.stroke);
    }
    if (roof) roof.setAttribute('fill', palette.roof);
    if (glass1) glass1.setAttribute('fill', palette.glass);
    if (glass2) glass2.setAttribute('fill', palette.glass);
  }

  spawnCar(car) {
    // 1. Exclude routes currently used by other active cars
    const occupiedRoutes = this.cars
      .filter((c) => c !== car && c.state === 'driving')
      .map((c) => c.routeIdx);

    // 2. Don't spawn if another active car is currently near the start point
    const availableIndices = PREPARED_ROUTES.map((_, idx) => idx).filter((idx) => {
      if (occupiedRoutes.includes(idx)) return false;
      const startPt = PREPARED_ROUTES[idx].pts[0];
      const isEntryBusy = this.cars.some((c) => {
        if (c === car || c.state !== 'driving') return false;
        return Math.hypot(c.x - startPt[0], c.y - startPt[1]) < 18.0;
      });
      return !isEntryBusy;
    });

    if (availableIndices.length === 0) {
      // Entry points momentarily busy: retry shortly
      car.waitTimer = 1.0;
      return;
    }

    const selectedRouteIdx = availableIndices[Math.floor(Math.random() * availableIndices.length)];

    car.routeIdx = selectedRouteIdx;
    car.dist = 0;
    car.baseSpeed = 8.0 + Math.random() * 2.2;
    car.currentSpeed = car.baseSpeed;
    car.state = 'driving';
    car.opacity = 0;
    car.blockedTime = 0;
    this.updateCarPalette(car);

    // Initial position & heading
    const r = PREPARED_ROUTES[car.routeIdx];
    car.x = r.pts[0][0];
    car.y = r.pts[0][1];
    car.heading = r.segs[0].ang;
    car.element.setAttribute(
      'transform',
      `translate(${car.x.toFixed(2)}, ${car.y.toFixed(2)}) rotate(${car.heading.toFixed(1)})`
    );
  }

  tick(timestamp) {
    if (!this.lastTimestamp) this.lastTimestamp = timestamp;
    const rawDt = (timestamp - this.lastTimestamp) / 1000;
    this.lastTimestamp = timestamp;

    // Clamp dt to prevent jumping after tab switches
    const dt = Math.min(0.08, Math.max(0.001, rawDt));

    // 1. Process waiting cars
    for (const car of this.cars) {
      if (car.state === 'waiting') {
        car.waitTimer -= dt;
        if (car.waitTimer <= 0) {
          this.spawnCar(car);
        }
      }
    }

    // 2. Anti-collision check & deadlock avoidance for driving cars
    for (const car of this.cars) {
      if (car.state !== 'driving') continue;

      let speedFactor = 1.0;
      const rad = (car.heading * Math.PI) / 180;
      const cosA = Math.cos(rad);
      const sinA = Math.sin(rad);

      for (const other of this.cars) {
        if (other === car || other.state !== 'driving') continue;

        const dx = other.x - car.x;
        const dy = other.y - car.y;
        const dist = Math.hypot(dx, dy);

        if (dist >= 14.0) continue;

        const forwardDist = dx * cosA + dy * sinA;
        const lateralDist = Math.abs(-dx * sinA + dy * cosA);

        // Forward corridor following (in-lane traffic ahead)
        if (forwardDist > 0.5 && lateralDist < 2.4) {
          const clearance = Math.max(0, (forwardDist - 5.5) / 5.5);
          speedFactor = Math.min(speedFactor, clearance);
        }
        // Intersection merge yield: if cars get too close, the car with higher ID yields
        else if (dist < 5.5) {
          if (car.id > other.id) {
            const clearance = Math.max(0, (dist - 4.0) / 1.5);
            speedFactor = Math.min(speedFactor, clearance);
          }
        }
      }

      // Anti-deadlock watchdog: if car is stopped / blocked for > 2.0s, despawn to guarantee free flow
      if (speedFactor < 0.25) {
        car.blockedTime = (car.blockedTime || 0) + dt;
        if (car.blockedTime > 2.0) {
          car.state = 'waiting';
          car.opacity = 0;
          car.element.style.opacity = '0';
          car.waitTimer = 1.5 + Math.random() * 2.0;
          car.blockedTime = 0;
          continue;
        }
      } else {
        car.blockedTime = 0;
      }

      car.currentSpeed = car.baseSpeed * speedFactor;
    }

    // 3. Update positions along routes
    for (const car of this.cars) {
      if (car.state !== 'driving') continue;

      const r = PREPARED_ROUTES[car.routeIdx];
      car.dist += car.currentSpeed * dt;

      if (car.dist >= r.total) {
        // Finished route: fade out and wait before next random trip
        car.state = 'waiting';
        car.opacity = 0;
        car.element.style.opacity = '0';
        car.waitTimer = 2.5 + Math.random() * 4.0;
        continue;
      }

      // Find current segment along route
      let sIdx = 0;
      while (sIdx < r.segs.length - 1 && car.dist > r.segs[sIdx + 1].startDist) {
        sIdx++;
      }
      const seg = r.segs[sIdx];
      const segT = Math.max(0, Math.min(1, (car.dist - seg.startDist) / seg.len));

      car.x = seg.p1[0] + segT * (seg.p2[0] - seg.p1[0]);
      car.y = seg.p1[1] + segT * (seg.p2[1] - seg.p1[1]);

      // Smooth steering heading interpolation
      const headingDiff = normalizeDeg(seg.ang - car.heading);
      car.heading += headingDiff * Math.min(1.0, 10.0 * dt);

      // Smooth fade-in at start, fade-out at end
      const fadeInDist = 14.0;
      const fadeOutDist = 14.0;
      if (car.dist < fadeInDist) {
        car.opacity = Math.min(1.0, car.dist / fadeInDist);
      } else if (car.dist > r.total - fadeOutDist) {
        car.opacity = Math.max(0.0, (r.total - car.dist) / fadeOutDist);
      } else {
        car.opacity = 1.0;
      }

      // Update SVG transform
      car.element.setAttribute(
        'transform',
        `translate(${car.x.toFixed(2)}, ${car.y.toFixed(2)}) rotate(${car.heading.toFixed(1)})`
      );
      car.element.style.opacity = car.opacity.toFixed(2);
    }

    this.animId = requestAnimationFrame(this.boundTick);
  }

  handleVisibilityChange() {
    if (document.hidden) {
      if (this.animId) {
        cancelAnimationFrame(this.animId);
        this.animId = null;
      }
    } else {
      this.lastTimestamp = null;
      if (!this.animId) {
        this.animId = requestAnimationFrame(this.boundTick);
      }
    }
  }

  destroy() {
    if (this.animId) {
      cancelAnimationFrame(this.animId);
      this.animId = null;
    }
    document.removeEventListener('visibilitychange', this.boundVisibility);
    this.cars = [];
    if (this.container) {
      this.container.innerHTML = '';
    }
  }
}
