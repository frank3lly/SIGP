/**
 * SGIP - Central Reactive State Store
 */

export class Store {
  constructor(initialState = {}) {
    this.state = {
      spots: {},
      stats: { total: 0, occupied: 0, free: 0, rate: 0.0 },
      activeSpotId: null,
      filter: 'all', // 'all', 'free', 'occupied'
      isConnected: false,
      adminToken: typeof sessionStorage !== 'undefined'
        ? sessionStorage.getItem('parqueame_admin_token')
        : null,
      adminActive: false,
      ...initialState,
    };
    this.listeners = new Set();
  }

  getState() {
    return this.state;
  }

  setState(updates) {
    this.state = { ...this.state, ...updates };
    this.notify();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify() {
    this.listeners.forEach((fn) => {
      try {
        fn(this.state);
      } catch (err) {
        console.error('Error in state subscriber:', err);
      }
    });
  }
}
