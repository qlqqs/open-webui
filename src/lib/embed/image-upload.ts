// sub2api-embed: local image conversions must not fetch data: URLs under connect-src 'self'.
export function readImageDataURL(file: File): Promise<string> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => {
			if (typeof reader.result === 'string') resolve(reader.result);
			else reject(new Error('Unable to read image'));
		};
		reader.onerror = () => reject(reader.error ?? new Error('Unable to read image'));
		reader.onabort = () => reject(new Error('Image read aborted'));
		reader.readAsDataURL(file);
	});
}

export function imageDataURLToFile(dataURL: string, original: File, originalURL: string): File {
	// No compression (including already-small images): preserve exact bytes and metadata.
	if (dataURL === originalURL) return original;
	const match = /^data:(image\/[a-z0-9.+-]+);base64,([\s\S]*)$/i.exec(dataURL);
	if (!match) throw new Error('Invalid image data URL');
	const bytes = Uint8Array.from(atob(match[2]), (char) => char.charCodeAt(0));
	return new File([bytes], original.name, { type: match[1], lastModified: original.lastModified });
}

export function canvasImageFile(canvas: HTMLCanvasElement, name: string): Promise<File> {
	return new Promise((resolve, reject) => {
		canvas.toBlob((blob) => {
			if (blob) resolve(new File([blob], name, { type: blob.type }));
			else reject(new Error('Unable to encode image'));
		}, 'image/png');
	});
}
