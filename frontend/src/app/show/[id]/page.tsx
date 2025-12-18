'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Tv, CheckCircle, Clock, AlertCircle, RefreshCw, Loader2 } from 'lucide-react'
import { api, MediaItem } from '@/lib/api'

// Episode type for this page
interface EpisodeData {
    id: number
    season_number: number
    episode_number: number
    title: string | null
    overview: string | null
    air_date: string | null
    state: string
    file_path: string | null
    symlink_path: string | null
}

interface EpisodesResponse {
    show_id: number
    show_title: string
    total_episodes: number
    completed_episodes: number
    episodes: EpisodeData[]
}

const stateColors: Record<string, string> = {
    completed: 'bg-green-500/20 text-green-400',
    symlinked: 'bg-green-500/20 text-green-400',
    downloaded: 'bg-blue-500/20 text-blue-400',
    downloading: 'bg-blue-500/20 text-blue-400',
    scraped: 'bg-yellow-500/20 text-yellow-400',
    indexed: 'bg-yellow-500/20 text-yellow-400',
    requested: 'bg-gray-500/20 text-gray-400',
    failed: 'bg-red-500/20 text-red-400',
    paused: 'bg-gray-500/20 text-gray-400',
}

const stateIcons: Record<string, any> = {
    completed: CheckCircle,
    symlinked: CheckCircle,
    downloaded: Clock,
    downloading: Loader2,
    scraped: Clock,
    indexed: Clock,
    requested: Clock,
    failed: AlertCircle,
    paused: Clock,
}

export default function ShowDetailPage() {
    const params = useParams()
    const router = useRouter()
    const showId = params.id as string

    const [show, setShow] = useState<MediaItem | null>(null)
    const [episodesData, setEpisodesData] = useState<EpisodesResponse | null>(null)
    const [loading, setLoading] = useState(true)
    const [retrying, setRetrying] = useState<number | null>(null)

    const fetchData = async () => {
        try {
            const [showData, epData] = await Promise.all([
                api.getMediaItem(parseInt(showId)),
                fetch(`/api/library/${showId}/episodes`)
                    .then(r => r.json())
            ])
            setShow(showData)
            setEpisodesData(epData)
        } catch (error) {
            console.error('Failed to fetch show data:', error)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchData()
        // Poll for updates every 30 seconds
        const interval = setInterval(fetchData, 30000)
        return () => clearInterval(interval)
    }, [showId])

    const retryEpisode = async (episodeId: number) => {
        setRetrying(episodeId)
        try {
            await fetch(
                `/api/library/${showId}/episodes/${episodeId}/retry`,
                { method: 'POST' }
            )
            await fetchData()
        } catch (error) {
            console.error('Failed to retry episode:', error)
        } finally {
            setRetrying(null)
        }
    }

    // Group episodes by season
    const episodesBySeason = episodesData?.episodes.reduce((acc, ep) => {
        const season = ep.season_number
        if (!acc[season]) acc[season] = []
        acc[season].push(ep)
        return acc
    }, {} as Record<number, EpisodeData[]>) || {}

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary-500"></div>
            </div>
        )
    }

    if (!show) {
        return (
            <div className="text-center py-20">
                <p className="text-gray-400">Show not found</p>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-start gap-6">
                <button
                    onClick={() => router.back()}
                    className="p-2 rounded-lg hover:bg-white/10 transition-colors"
                >
                    <ArrowLeft className="w-6 h-6" />
                </button>

                {show.poster_url && (
                    <img
                        src={show.poster_url}
                        alt={show.title}
                        className="w-32 h-48 object-cover rounded-lg shadow-lg"
                    />
                )}

                <div className="flex-1">
                    <h1 className="text-3xl font-bold">{show.title}</h1>
                    {show.year && (
                        <p className="text-gray-400">{show.year}</p>
                    )}

                    <div className="flex items-center gap-4 mt-4">
                        <div className="flex items-center gap-2 text-primary-400">
                            <Tv className="w-5 h-5" />
                            <span>{show.number_of_seasons} Seasons</span>
                        </div>

                        {episodesData && (
                            <div className="flex items-center gap-2 text-green-400">
                                <CheckCircle className="w-5 h-5" />
                                <span>
                                    {episodesData.completed_episodes}/{episodesData.total_episodes} Episodes
                                </span>
                            </div>
                        )}
                    </div>

                    {show.overview && (
                        <p className="text-gray-400 mt-4 line-clamp-3">{show.overview}</p>
                    )}
                </div>
            </div>

            {/* Progress Bar */}
            {episodesData && episodesData.total_episodes > 0 && (
                <div className="glass rounded-xl p-4">
                    <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-400">Download Progress</span>
                        <span className="text-primary-400">
                            {Math.round((episodesData.completed_episodes / episodesData.total_episodes) * 100)}%
                        </span>
                    </div>
                    <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-primary-500 to-accent-500 transition-all duration-500"
                            style={{ width: `${(episodesData.completed_episodes / episodesData.total_episodes) * 100}%` }}
                        />
                    </div>
                </div>
            )}

            {/* Seasons */}
            <div className="space-y-4">
                {Object.entries(episodesBySeason).map(([season, episodes]) => (
                    <div key={season} className="glass rounded-xl overflow-hidden">
                        <div className="p-4 border-b border-white/10">
                            <h2 className="text-xl font-semibold">Season {season}</h2>
                            <p className="text-sm text-gray-400">
                                {episodes.filter(e => e.state === 'completed').length}/{episodes.length} completed
                            </p>
                        </div>

                        <div className="divide-y divide-white/5">
                            {episodes.map((ep) => {
                                const StateIcon = stateIcons[ep.state] || Clock
                                const isRetrying = retrying === ep.id

                                return (
                                    <div
                                        key={ep.id}
                                        className="p-4 flex items-center gap-4 hover:bg-white/5 transition-colors"
                                    >
                                        <div className="w-12 h-12 rounded-lg bg-white/10 flex items-center justify-center">
                                            <span className="font-bold text-lg">{ep.episode_number}</span>
                                        </div>

                                        <div className="flex-1 min-w-0">
                                            <p className="font-medium truncate">
                                                {ep.title || `Episode ${ep.episode_number}`}
                                            </p>
                                            {ep.air_date && (
                                                <p className="text-sm text-gray-500">{ep.air_date}</p>
                                            )}
                                        </div>

                                        <div className={`px-3 py-1 rounded-full text-xs font-medium flex items-center gap-1 ${stateColors[ep.state] || stateColors.requested}`}>
                                            <StateIcon className={`w-3 h-3 ${ep.state === 'downloading' ? 'animate-spin' : ''}`} />
                                            <span className="capitalize">{ep.state}</span>
                                        </div>

                                        {ep.state === 'failed' && (
                                            <button
                                                onClick={() => retryEpisode(ep.id)}
                                                disabled={isRetrying}
                                                className="p-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-400 transition-colors disabled:opacity-50"
                                            >
                                                {isRetrying ? (
                                                    <Loader2 className="w-4 h-4 animate-spin" />
                                                ) : (
                                                    <RefreshCw className="w-4 h-4" />
                                                )}
                                            </button>
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                ))}
            </div>

            {Object.keys(episodesBySeason).length === 0 && (
                <div className="text-center py-12 glass rounded-xl">
                    <Clock className="w-12 h-12 text-gray-500 mx-auto mb-4" />
                    <p className="text-gray-400">Episodes are being indexed...</p>
                    <p className="text-sm text-gray-500 mt-2">Check back in a moment</p>
                </div>
            )}
        </div>
    )
}
