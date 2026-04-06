# Strips comment lines (starting with #) from CSV data files before Jekyll uses them.
# This lets you keep comments like "# run: python scripts/admin_server.py" in _data/*.csv
# without breaking site.data.* access.

require 'csv'

Jekyll::Hooks.register :site, :post_read do |site|
  data_dir = File.join(site.source, '_data')
  Dir.glob(File.join(data_dir, '*.csv')).each do |csv_file|
    key = File.basename(csv_file, '.csv')
    content = File.read(csv_file, encoding: 'utf-8')
    next unless content.lines.any? { |l| l.strip.start_with?('#') }

    stripped = content.lines.reject { |l| l.strip.start_with?('#') }.join
    parsed = CSV.parse(stripped, headers: true)
    site.data[key] = parsed.map(&:to_h)
  end
end
