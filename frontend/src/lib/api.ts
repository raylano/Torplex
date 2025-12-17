/**
 * Torplex API Client
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface MediaItem {
    id: number
    imdb_id: string | null
    tmdb_id: number | null
    title: string
    original_title: string | null
    year: number | null
    type: string
    state: string
    is_anime: boolean
    poster_path: string | null
    backdrop_path: string | null
    overview: string | null
    genres: string[] | null
    vote_average: number | null
    number_of_seasons: number | null
    number_of_episodes: number | null
    status: string | null
    file_path: string | null
    symlink_path: string | null
    last_error: string | null
    retry_count: number
    created_at: string
    updated_at: string
    completed_at: string | null
    poster_url: string | null
    backdrop_url: string | null
}

export interface Stats {
    providers: Record<string, boolean>
    mount_status: boolean
    counts: {
        requested: number
        indexed: number
        scraped: number
        downloading: number
        downloaded: number
        symlinked: number
        completed: number
        failed: number
        paused: number
    }
    total: number
}

export interface PaginatedResponse<T> {
    items: T[]
    total: number
    page: number
    page_size: number
    total_pages: number
}

export interface SearchResult {
    id: number
    title: string
    original_title: string | null
    year: number | null
    type: string
    poster_path: string | null
    backdrop_path: string | null
    overview: string | null
    vote_average: number | null
    poster_url: string | null
    backdrop_url: string | null
}

export interface LibraryFilters {
    page?: number
    pageSize?: number
    type?: string
    state?: string
    isAnime?: boolean
    search?: string
}

async function fetchAPI<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${API_URL}${endpoint}`

    const response = await fetch(url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    })

    if (!response.ok) {
        throw new Error(`API error: ${response.status} ${response.statusText}`)
    }

    return response.json()
}

export const api = {
    // Health
    async getHealth() {
        return fetchAPI<{ status: string; timestamp: string; version: string }>('/api/health')
    },

    // Stats
    async getStats() {
        return fetchAPI<Stats>('/api/stats')
    },

    // Library
    async getLibrary(filters: LibraryFilters = {}) {
        const params = new URLSearchParams()
        if (filters.page) params.append('page', filters.page.toString())
        if (filters.pageSize) params.append('page_size', filters.pageSize.toString())
        if (filters.type) params.append('type', filters.type)
        if (filters.state) params.append('state', filters.state)
        if (filters.isAnime !== undefined) params.append('is_anime', filters.isAnime.toString())
        if (filters.search) params.append('search', filters.search)

        return fetchAPI<PaginatedResponse<MediaItem>>(`/api/library?${params}`)
    },

    async getMediaItem(id: number) {
        return fetchAPI<MediaItem>(`/api/library/${id}`)
    },

    async createMediaItem(data: {
        title: string
        year?: number
        type?: string
        imdb_id?: string
        tmdb_id?: number
        is_anime?: boolean
    }) {
        return fetchAPI<MediaItem>('/api/library', {
            method: 'POST',
            body: JSON.stringify(data),
        })
    },

    async updateMediaItem(id: number, data: { state?: string; is_anime?: boolean }) {
        return fetchAPI<MediaItem>(`/api/library/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(data),
        })
    },

    async deleteMediaItem(id: number) {
        return fetchAPI<{ message: string; id: number }>(`/api/library/${id}`, {
            method: 'DELETE',
        })
    },

    async retryMediaItem(id: number) {
        return fetchAPI<{ message: string; id: number }>(`/api/library/${id}/retry`, {
            method: 'POST',
        })
    },

    // Search
    async search(query: string, type?: 'movie' | 'tv' | 'all') {
        const params = new URLSearchParams({ query })
        if (type) params.append('type', type)

        return fetchAPI<SearchResult[]>(`/api/search?${params}`)
    },

    async getTrending(type: 'all' | 'movie' | 'tv' = 'all') {
        return fetchAPI<{ results: SearchResult[] }>(`/api/trending?type=${type}`)
    },

    async getMovieDetails(tmdbId: number) {
        return fetchAPI<any>(`/api/search/movie/${tmdbId}`)
    },

    async getTvDetails(tmdbId: number) {
        return fetchAPI<any>(`/api/search/tv/${tmdbId}`)
    },

    // Settings
    async getSettings() {
        return fetchAPI<any>('/api/settings')
    },

    async getProviderStatus() {
        return fetchAPI<{ providers: any[] }>('/api/settings/providers/status')
    },
}
