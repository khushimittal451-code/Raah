import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom has no native SVG feature probe; enable Leaflet's SVG path for DOM integration checks.
SVGSVGElement.prototype.createSVGRect = () => ({});

afterEach(() => cleanup());
