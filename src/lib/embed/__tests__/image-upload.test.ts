import { afterEach, describe, expect, it, vi } from 'vitest';
import { canvasImageFile, imageDataURLToFile, readImageDataURL } from '../image-upload';

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('CSP-safe image upload', () => {
	it('preserves the original file without compression, including metadata', () => {
		const original = new File(['original'], 'photo.png', { type: 'image/png', lastModified: 123 });
		expect(imageDataURLToFile('unchanged', original, 'unchanged')).toBe(original);
	});

	it('decodes compressed bytes locally and uses the encoded MIME type', async () => {
		const fetch = vi.fn(() => {
			throw new Error('CSP forbids data: fetch');
		});
		vi.stubGlobal('fetch', fetch);
		const original = new File(['original'], 'photo.webp', {
			type: 'image/webp',
			lastModified: 123
		});
		const file = imageDataURLToFile('data:image/png;base64,AP+A', original, 'original');
		expect([...new Uint8Array(await file.arrayBuffer())]).toEqual([0, 255, 128]);
		expect(file.type).toBe('image/png');
		expect(file.name).toBe(original.name);
		expect(file.lastModified).toBe(123);
		expect(fetch).not.toHaveBeenCalled();
	});

	it.each([
		'https://example.com/image.png',
		'data:text/html;base64,AA==',
		'data:image/png;base64,%%%'
	])('rejects invalid or non-image data: %s', (url) => {
		expect(() => imageDataURLToFile(url, new File([], 'photo.png'), 'original')).toThrow();
	});

	it('reads the original data URL', async () => {
		vi.stubGlobal(
			'FileReader',
			class {
				result = 'data:image/png;base64,AA==';
				onload!: () => void;
				readAsDataURL() {
					this.onload();
				}
			}
		);
		await expect(readImageDataURL(new File([], 'photo.png'))).resolves.toBe(
			'data:image/png;base64,AA=='
		);
	});

	it.each(['onerror', 'onabort'] as const)(
		'rejects FileReader %s instead of hanging',
		async (event) => {
			vi.stubGlobal(
				'FileReader',
				class {
					onerror!: () => void;
					onabort!: () => void;
					readAsDataURL() {
						this[event]();
					}
				}
			);
			await expect(readImageDataURL(new File([], 'photo.png'))).rejects.toThrow();
		}
	);

	it('rejects non-string read results', async () => {
		vi.stubGlobal(
			'FileReader',
			class {
				result = null;
				onload!: () => void;
				readAsDataURL() {
					this.onload();
				}
			}
		);
		await expect(readImageDataURL(new File([], 'photo.png'))).rejects.toThrow();
	});

	it('encodes screenshots directly with toBlob', async () => {
		const toBlob = vi.fn((callback: BlobCallback) =>
			callback(new Blob(['png'], { type: 'image/png' }))
		);
		const file = await canvasImageFile({ toBlob } as unknown as HTMLCanvasElement, 'screen.png');
		expect(file.name).toBe('screen.png');
		expect(file.type).toBe('image/png');
		expect(await file.text()).toBe('png');
		expect(toBlob).toHaveBeenCalledWith(expect.any(Function), 'image/png');
	});

	it('rejects failed canvas encoding', async () => {
		const canvas = { toBlob: (callback: BlobCallback) => callback(null) } as HTMLCanvasElement;
		await expect(canvasImageFile(canvas, 'screen.png')).rejects.toThrow('Unable to encode');
	});
});
