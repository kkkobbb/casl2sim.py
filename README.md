# casl2sim.py
CASL2シミュレータ

## デフォルトの動作
* PR以外のレジスタは0で初期化される
* PRは`START`で指定したアドレスで初期化される
* コード以外のメモリは0xffff番地まで0で初期化される
* `IN`の入力元は標準入力
* `OUT`の出力先は標準出力
* `OUT`の出力には先頭に`  OUT: `が付く
* デバッグ情報を標準出力に出力する

## 実行例
* デフォルト
    * `./casl2sim.py casl2file`
* デバッグ情報非表示
    * `./casl2sim.py --output-debug= casl2file`
* `RET`で実行終了するコードを実行する
    * `./casl2sim.py --virtual-call casl2file`
* `IN`の際、ファイル`infile`を入力として使用する
    * `./casl2sim.py --input-src=infile casl2file`
* `OUT`の際、ファイル`outfile`に出力する
    * `./casl2sim.py --output=outfile casl2file`
