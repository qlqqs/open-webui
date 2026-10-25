// sub2api embed: no third-party requests from the page (CSP img-src / connect-src 'self').
export const NEUTRAL_LINK_ICON = '/embed/link.svg';

/** Favicon for a cited site: Google's favicon service upstream, a local globe icon in embed mode. */
export function siteFavicon(domain: string, embed: boolean): string {
	return embed ? NEUTRAL_LINK_ICON : `https://www.google.com/s2/favicons?sz=32&domain=${domain}`;
}

/** Search-engine link for a web search query; none in embed mode (the search ran upstream). */
export function searchQueryLink(query: string, embed: boolean): string | undefined {
	return embed ? undefined : `https://www.google.com/search?q=${query}`;
}
