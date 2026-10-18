'use strict';
// Test page for the live protocol (see PROTOCOL.md): waiting room, clock sync, pose stream and latency stats.
// The real viewer replaces this page.

(function () {
	const T = {
		Welcome: 0x01, Waiting: 0x02, Approved: 0x03, Denied: 0x04, Revoked: 0x05, Pong: 0x06,
		SessionStart: 0x10, SessionEnd: 0x11, Idle: 0x12,
		Pose: 0x20, NoteCut: 0x21, NoteFinal: 0x22, Wall: 0x23, Height: 0x24, Pause: 0x25, Resume: 0x26,
		MapChunk: 0x30, MapError: 0x31,
		Hello: 0x81, Ping: 0x82, MapRequest: 0x83,
	};
	const CREDENTIAL_KEY = 'bslive.credential';

	const $ = id => document.getElementById(id);
	const stats = {
		state: 'connecting', code: null, session: null, sessionId: 0,
		poses: 0, posesPerSecond: 0, noteCuts: 0, noteFinals: 0, walls: 0,
		rttMs: null, offsetUs: null,
		receiveAgeMs: null, displayAgeMs: null, maxReceiveAgeMs: 0,
		lastPose: null, lastPoseReceivedAt: 0,
		maps: {},
	};
	window.liveStats = stats; // for automated tests

	// ---- storage (may be unavailable) ----
	function loadCredential() {
		try {
			const hex = localStorage.getItem(CREDENTIAL_KEY);
			if (!hex || !/^[0-9a-f]{64}$/.test(hex)) return null;
			return Uint8Array.from(hex.match(/../g).map(h => parseInt(h, 16)));
		} catch (e) {
			return null;
		}
	}
	function saveCredential(bytes) {
		try {
			if (bytes) localStorage.setItem(CREDENTIAL_KEY, Array.from(bytes, b => b.toString(16).padStart(2, '0')).join(''));
			else localStorage.removeItem(CREDENTIAL_KEY);
		} catch (e) { /* ignore */ }
	}

	// ---- binary helpers ----
	class Reader {
		constructor(buffer) { this.v = new DataView(buffer); this.p = 0; }
		u8() { return this.v.getUint8(this.p++); }
		u16() { const x = this.v.getUint16(this.p, true); this.p += 2; return x; }
		u32() { const x = this.v.getUint32(this.p, true); this.p += 4; return x; }
		i32() { const x = this.v.getInt32(this.p, true); this.p += 4; return x; }
		i64() { const x = this.v.getBigInt64(this.p, true); this.p += 8; return Number(x); }
		f32() { const x = this.v.getFloat32(this.p, true); this.p += 4; return x; }
		f64() { const x = this.v.getFloat64(this.p, true); this.p += 8; return x; }
		bytes(n) { const b = new Uint8Array(this.v.buffer, this.p, n); this.p += n; return b; }
		str() { const n = this.i32(); return new TextDecoder().decode(this.bytes(n)); }
		vec3() { return {x: this.f32(), y: this.f32(), z: this.f32()}; }
		quat() { return {x: this.f32(), y: this.f32(), z: this.f32(), w: this.f32()}; }
		pose() { return {position: this.vec3(), rotation: this.quat()}; }
	}

	function message(type, size, fill) {
		const buf = new ArrayBuffer(1 + size);
		const v = new DataView(buf);
		v.setUint8(0, type);
		if (fill) fill(v, new Uint8Array(buf));
		return buf;
	}

	// ---- connection ----
	let ws = null;
	let pingTimer = null;
	const pongs = [];
	let nextRequestId = 1;
	const transfers = {};

	function connect() {
		stats.state = 'connecting';
		render();
		ws = new WebSocket(`wss://${location.host}/ws`, 'bslive.v1');
		ws.binaryType = 'arraybuffer';
		ws.onopen = () => {
			const credential = loadCredential();
			// Protocol 2: the test page always waits under the name "Test page".
			const name = new TextEncoder().encode('Test page');
			const at = 4 + (credential ? 32 : 0);
			ws.send(message(T.Hello, at + 3 + name.length, (v, b) => {
				v.setUint16(1, 2, true);
				v.setUint8(3, credential ? 1 : 0);
				if (credential) b.set(credential, 4);
				v.setInt32(at, name.length, true);
				b.set(name, at + 4);
			}));
			ping();
			pingTimer = setInterval(ping, 1000);
		};
		ws.onmessage = e => onMessage(e.data);
		ws.onclose = () => {
			clearInterval(pingTimer);
			if (stats.state === 'denied' || stats.state === 'revoked') return render();
			stats.state = 'disconnected';
			render();
			setTimeout(connect, 2000);
		};
	}

	function ping() {
		if (ws.readyState !== WebSocket.OPEN) return;
		ws.send(message(T.Ping, 8, v => v.setFloat64(1, performance.now(), true)));
	}

	function onMessage(data) {
		const r = new Reader(data);
		const type = r.u8();
		switch (type) {
			case T.Welcome:
				r.u16(); r.i64(); stats.serverName = r.str();
				break;
			case T.Waiting:
				stats.state = 'waiting';
				stats.code = r.str();
				saveCredential(null); // a stored credential, if any, wasn't accepted
				break;
			case T.Approved: {
				stats.state = 'approved';
				if (r.u8()) saveCredential(r.bytes(32).slice());
				break;
			}
			case T.Denied: stats.state = 'denied'; break;
			case T.Revoked: stats.state = 'revoked'; saveCredential(null); break;
			case T.Pong: onPong(r); break;
			case T.SessionStart:
				stats.sessionId = r.u32();
				stats.session = JSON.parse(r.str());
				stats.noteCuts = stats.noteFinals = stats.walls = 0;
				break;
			case T.SessionEnd: stats.session = null; break;
			case T.Idle: stats.session = null; break;
			case T.Pose: onPose(r); break;
			case T.NoteCut: stats.noteCuts++; break;
			case T.NoteFinal: stats.noteFinals++; break;
			case T.Wall: stats.walls++; break;
			case T.MapChunk: onMapChunk(r, data); break;
			case T.MapError: {
				const id = r.u16(), code = r.u8();
				const t = transfers[id];
				if (t) { log(`${t.name}: error ${code}`); delete transfers[id]; }
				break;
			}
		}
		if (type !== T.Pose) render();
	}

	// Clock sync: offset = server - client (µs); keep the lowest-RTT sample of the last 16.
	function onPong(r) {
		const t1 = performance.now();
		const t0 = r.f64(), sr = r.i64(), ss = r.i64();
		const rttUs = (t1 - t0) * 1000 - (ss - sr);
		const offsetUs = (sr + ss) / 2 - ((t0 + t1) / 2) * 1000;
		pongs.push({rttUs, offsetUs});
		if (pongs.length > 16) pongs.shift();
		const best = pongs.reduce((a, b) => (b.rttUs < a.rttUs ? b : a));
		stats.rttMs = best.rttUs / 1000;
		stats.offsetUs = best.offsetUs;
	}

	const poseTimes = [];
	function onPose(r) {
		const now = performance.now();
		const captureUs = r.i64();
		const pose = {captureUs, songTime: r.f32(), head: r.pose(), left: r.pose(), right: r.pose()};
		stats.poses++;
		stats.lastPose = pose;
		stats.lastPoseReceivedAt = now;
		poseTimes.push(now);
		while (poseTimes.length && poseTimes[0] < now - 1000) poseTimes.shift();
		stats.posesPerSecond = poseTimes.length;
		if (stats.offsetUs !== null) {
			stats.receiveAgeMs = (now * 1000 - (captureUs - stats.offsetUs)) / 1000;
			stats.maxReceiveAgeMs = Math.max(stats.maxReceiveAgeMs, stats.receiveAgeMs);
		}
	}

	// ---- map download test ----
	function requestMapFiles() {
		if (!stats.session) return log('No session.');
		for (const [role, name] of Object.entries(stats.session.files)) {
			const id = nextRequestId++ & 0xffff;
			const nameBytes = new TextEncoder().encode(name);
			transfers[id] = {name: `${role} (${name})`, parts: [], received: 0, started: performance.now()};
			ws.send(message(T.MapRequest, 2 + 4 + 4 + nameBytes.length, (v, b) => {
				v.setUint16(1, id, true);
				v.setUint32(3, stats.sessionId, true);
				v.setInt32(7, nameBytes.length, true);
				b.set(nameBytes, 11);
			}));
		}
	}

	function onMapChunk(r, data) {
		const id = r.u16(), total = r.u32(), offset = r.u32();
		const t = transfers[id];
		if (!t) return;
		const chunk = new Uint8Array(data, r.p);
		t.parts.push(chunk.slice());
		t.received += chunk.length;
		if (t.received >= total) {
			const ms = performance.now() - t.started;
			stats.maps[t.name] = total;
			log(`${t.name}: ${total} bytes in ${ms.toFixed(0)} ms`);
			delete transfers[id];
		}
	}

	function log(line) { $('maplog').textContent += line + '\n'; }

	// ---- rendering ----
	function render() {
		const s = stats;
		const states = {
			connecting: 'Connecting…',
			waiting: 'Waiting for approval',
			approved: 'Connected',
			denied: 'Not allowed. Reload the page to ask again.',
			revoked: 'Access was revoked.',
			disconnected: 'Disconnected, retrying…',
		};
		$('state').textContent = states[s.state] || s.state;
		$('code').hidden = s.state !== 'waiting';
		$('code').textContent = s.code || '';
		$('hint').textContent = s.state === 'waiting' ? 'Ask the player to allow this code in the Live Viewer menu.' : '';
		$('live').hidden = s.state !== 'approved';
		$('song').textContent = s.session
			? `${s.session.songName} — ${s.session.mode} ${s.session.difficulty} (${s.session.playerName})`
			: 'No song playing';
	}

	function fmt(x, digits = 1) { return x === null || x === undefined ? '–' : x.toFixed(digits); }

	function renderStats() {
		const s = stats;
		const rows = [
			['Poses / s', s.posesPerSecond],
			['Sample age at receipt (ms)', fmt(s.receiveAgeMs)],
			['Sample age at display (ms)', fmt(s.displayAgeMs)],
			['Max age at receipt (ms)', fmt(s.maxReceiveAgeMs)],
			['Round trip (ms)', fmt(s.rttMs)],
			['Note cuts / finals', `${s.noteCuts} / ${s.noteFinals}`],
			['Song time (s)', s.lastPose ? fmt(s.lastPose.songTime, 2) : '–'],
		];
		$('stats').innerHTML = '';
		for (const [k, v] of rows) {
			const tr = document.createElement('tr');
			const a = document.createElement('td');
			const b = document.createElement('td');
			a.textContent = k;
			b.textContent = String(v);
			tr.append(a, b);
			$('stats').append(tr);
		}
	}

	// Rotate (0, 0, 1) by a quaternion.
	function forward(q) {
		return {
			x: 2 * (q.x * q.z + q.w * q.y),
			y: 2 * (q.y * q.z - q.w * q.x),
			z: 1 - 2 * (q.x * q.x + q.y * q.y),
		};
	}

	const canvas = $('view');
	const ctx = canvas.getContext('2d');
	function draw() {
		const now = performance.now();
		const p = stats.lastPose;
		if (p && stats.offsetUs !== null) {
			stats.displayAgeMs = (now * 1000 - (p.captureUs - stats.offsetUs)) / 1000;
		}
		const css = getComputedStyle(document.documentElement);
		ctx.clearRect(0, 0, canvas.width, canvas.height);
		if (p) {
			// Front view: x right, y up; 1 m = 120 px; floor at the bottom.
			const sx = x => canvas.width / 2 + x * 120;
			const sy = y => canvas.height - 20 - y * 120;
			const saber = (pose, color) => {
				const f = forward(pose.rotation);
				ctx.strokeStyle = color;
				ctx.lineWidth = 5;
				ctx.beginPath();
				ctx.moveTo(sx(pose.position.x), sy(pose.position.y));
				ctx.lineTo(sx(pose.position.x + f.x), sy(pose.position.y + f.y));
				ctx.stroke();
			};
			saber(p.left, css.getPropertyValue('--left'));
			saber(p.right, css.getPropertyValue('--right'));
			ctx.fillStyle = css.getPropertyValue('--fg');
			ctx.beginPath();
			ctx.arc(sx(p.head.position.x), sy(p.head.position.y), 14, 0, Math.PI * 2);
			ctx.fill();
		}
		renderStats();
		requestAnimationFrame(draw);
	}

	$('maptest').addEventListener('click', requestMapFiles);
	render();
	connect();
	requestAnimationFrame(draw);
})();
