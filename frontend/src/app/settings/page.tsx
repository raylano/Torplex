'use client'

import { useState, useEffect } from 'react'
import { Settings as SettingsIcon, CheckCircle, XCircle, RefreshCw, Server, Database, HardDrive } from 'lucide-react'
import { api } from '@/lib/api'
import { clsx } from 'clsx'

export default function SettingsPage() {
    const [settings, setSettings] = useState<any>(null)
    const [providerStatus, setProviderStatus] = useState<any[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        async function fetchData() {
            try {
                const [settingsData, statusData] = await Promise.all([
                    api.getSettings(),
                    api.getProviderStatus(),
                ])
                setSettings(settingsData)
                setProviderStatus(statusData.providers)
            } catch (error) {
                console.error('Failed to fetch settings:', error)
            } finally {
                setLoading(false)
            }
        }
        fetchData()
    }, [])

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary-500"></div>
            </div>
        )
    }

    return (
        <div className="space-y-8 animate-fade-in max-w-4xl">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold gradient-text">Settings</h1>
                <p className="text-gray-400 mt-1">Configure your Torplex instance</p>
            </div>

            {/* Provider Status */}
            <section className="glass rounded-2xl p-6">
                <div className="flex items-center gap-3 mb-6">
                    <Server className="text-primary-400" size={20} />
                    <h2 className="text-xl font-semibold">Provider Status</h2>
                </div>

                <div className="space-y-4">
                    {providerStatus.map((provider) => (
                        <div
                            key={provider.name}
                            className={clsx(
                                'flex items-center justify-between p-4 rounded-xl',
                                provider.connected ? 'bg-green-500/10' : provider.configured ? 'bg-yellow-500/10' : 'bg-gray-500/10'
                            )}
                        >
                            <div className="flex items-center gap-4">
                                <div className={clsx(
                                    'w-3 h-3 rounded-full',
                                    provider.connected ? 'bg-green-400' : provider.configured ? 'bg-yellow-400' : 'bg-gray-500'
                                )} />
                                <div>
                                    <h3 className="font-medium">{provider.name}</h3>
                                    {provider.username && (
                                        <p className="text-sm text-gray-400">{provider.username}</p>
                                    )}
                                </div>
                            </div>
                            <div className="flex items-center gap-4">
                                {provider.premium && (
                                    <span className="px-2 py-1 text-xs font-medium rounded-full bg-accent-500/20 text-accent-400 border border-accent-500/30">
                                        Premium
                                    </span>
                                )}
                                {provider.connected ? (
                                    <CheckCircle className="text-green-400" size={20} />
                                ) : provider.configured ? (
                                    <RefreshCw className="text-yellow-400" size={20} />
                                ) : (
                                    <XCircle className="text-gray-500" size={20} />
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* Configuration */}
            <section className="glass rounded-2xl p-6">
                <div className="flex items-center gap-3 mb-6">
                    <SettingsIcon className="text-primary-400" size={20} />
                    <h2 className="text-xl font-semibold">Configuration</h2>
                </div>

                {settings?.providers && (
                    <div className="grid grid-cols-2 gap-4">
                        {Object.entries(settings.providers).map(([name, config]: [string, any]) => (
                            <div key={name} className="p-4 rounded-xl bg-white/5">
                                <h3 className="font-medium capitalize mb-2">{name.replace('_', ' ')}</h3>
                                <div className="space-y-1 text-sm text-gray-400">
                                    <p>Configured: {config.configured ? 'Yes' : 'No'}</p>
                                    {config.url && <p>URL: {config.url}</p>}
                                    {config.token_preview && <p>Token: {config.token_preview}</p>}
                                    {config.key_preview && <p>Key: {config.key_preview}</p>}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </section>

            {/* Paths */}
            <section className="glass rounded-2xl p-6">
                <div className="flex items-center gap-3 mb-6">
                    <HardDrive className="text-primary-400" size={20} />
                    <h2 className="text-xl font-semibold">Paths</h2>
                </div>

                {settings?.paths && (
                    <div className="space-y-4">
                        <div className="p-4 rounded-xl bg-white/5">
                            <label className="block text-sm text-gray-400 mb-1">Mount Path</label>
                            <code className="text-primary-300">{settings.paths.mount_path}</code>
                        </div>
                        <div className="p-4 rounded-xl bg-white/5">
                            <label className="block text-sm text-gray-400 mb-1">Symlink Path</label>
                            <code className="text-primary-300">{settings.paths.symlink_path}</code>
                        </div>
                    </div>
                )}
            </section>

            {/* Intervals */}
            <section className="glass rounded-2xl p-6">
                <div className="flex items-center gap-3 mb-6">
                    <Database className="text-primary-400" size={20} />
                    <h2 className="text-xl font-semibold">Scan Intervals</h2>
                </div>

                {settings?.intervals && (
                    <div className="grid grid-cols-2 gap-4">
                        <div className="p-4 rounded-xl bg-white/5">
                            <label className="block text-sm text-gray-400 mb-1">Watchlist Scan</label>
                            <p className="font-medium">{settings.intervals.watchlist_scan_interval}s</p>
                        </div>
                        <div className="p-4 rounded-xl bg-white/5">
                            <label className="block text-sm text-gray-400 mb-1">Library Scan</label>
                            <p className="font-medium">{settings.intervals.library_scan_interval}s</p>
                        </div>
                    </div>
                )}
            </section>

            {/* Info */}
            <div className="text-center text-sm text-gray-500">
                <p>Configuration is managed via environment variables.</p>
                <p>Restart the backend after changing .env values.</p>
            </div>
        </div>
    )
}
